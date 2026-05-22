"""Generate page-structured narrative JSON from ranked findings.

Strategy:
1. Rank findings by composite signal score.
2. For each page role, build a PageBrief containing only the findings that
   matter for that page (e.g. safety findings → page 4).
3. Call Claude with the system + per-page instructions. Claude returns a
   list of PageBlock-shaped JSON objects.
4. Fall back to a deterministic composer if Claude is unavailable so the
   pipeline always produces a section.
"""

from __future__ import annotations

import logging
from typing import Any

from clinical_evidence.narrative.claude_client import generate_page_blocks
from clinical_evidence.narrative.prompts import EXTRA_PAGE_ROLES, PAGE_ROLES, SYSTEM_PROMPT
from clinical_evidence.schemas import (
    CalloutBlock,
    Citation,
    ClinicalFinding,
    EndpointTableBlock,
    EndpointTableRow,
    EndpointType,
    EvidenceHierarchyBlock,
    EvidenceHierarchyEntry,
    FindingType,
    HeadingBlock,
    Page,
    PageBlock,
    ParagraphBlock,
    SafetyHeatmapBlock,
    SafetyHeatmapRow,
    SignalScores,
    Trial,
    TrialPhase,
    TrialTimelineBlock,
    TrialTimelineEntry,
    VerificationStatus,
)
from clinical_evidence.signal.risk import summarize as summarize_risks

log = logging.getLogger(__name__)


def _scores(f: ClinicalFinding) -> SignalScores:
    return f.scores if isinstance(f.scores, SignalScores) else SignalScores(**f.scores)


def _rank(findings: list[ClinicalFinding]) -> list[ClinicalFinding]:
    return sorted(findings, key=lambda f: _scores(f).composite(), reverse=True)


def _findings_for_page(
    role_idx: int,
    findings: list[ClinicalFinding],
) -> list[ClinicalFinding]:
    if role_idx == 1:
        return _rank(findings)[:6]
    if role_idx == 2:
        return [f for f in findings if f.finding_type in (FindingType.design.value, FindingType.design)] or _rank(findings)[:4]
    if role_idx == 3:
        eff = [f for f in findings if f.finding_type in (FindingType.efficacy.value, FindingType.efficacy)]
        return _rank(eff)[:8]
    if role_idx == 4:
        saf = [f for f in findings if f.finding_type in (FindingType.safety.value, FindingType.safety)]
        return _rank(saf)[:10]
    if role_idx == 5:
        return _rank(findings)[:5]
    if role_idx == 6:
        return [f for f in findings if f.risk_flags]
    if role_idx == 7:
        comp = [f for f in findings if f.finding_type in (FindingType.comparator.value, FindingType.comparator)]
        return _rank(comp)[:6]
    if role_idx == 8:
        sub = [f for f in findings if f.finding_type in (FindingType.subgroup.value, FindingType.subgroup)]
        return _rank(sub)[:6]
    if role_idx == 9:
        dur = [f for f in findings if f.finding_type in (FindingType.durability.value, FindingType.durability) or (f.follow_up_months and f.follow_up_months >= 12)]
        return _rank(dur)[:6]
    return _rank(findings)[:6]


def _brief(
    role_idx: int,
    findings: list[ClinicalFinding],
    citation_index: dict[str, int],
    company_name: str,
) -> dict[str, Any]:
    items = []
    for f in findings:
        s = _scores(f)
        items.append(
            {
                "finding_id": f.finding_id,
                "citation_number": citation_index.get(f.source_doc_id),
                "type": f.finding_type if isinstance(f.finding_type, str) else f.finding_type.value,
                "endpoint": f.endpoint,
                "endpoint_type": f.endpoint_type if isinstance(f.endpoint_type, str) else f.endpoint_type.value,
                "description": f.description,
                "raw_excerpt": f.raw_excerpt,
                "result": f.result.model_dump() if f.result else None,
                "follow_up_months": f.follow_up_months,
                "verification": f.verification_status if isinstance(f.verification_status, str) else f.verification_status.value,
                "composite_score": s.composite(),
                "scores": s.model_dump(),
                "risk_flags": [r if isinstance(r, str) else r.value for r in f.risk_flags],
            }
        )
    return {"page_index": role_idx, "company": company_name, "findings": items}


_BLOCK_SCHEMA = {
    "type": "array",
    "items": {
        "oneOf": [
            {"type": "object", "properties": {"kind": {"const": "paragraph"}, "text": {"type": "string"}, "citation_numbers": {"type": "array", "items": {"type": "integer"}}}, "required": ["kind", "text"]},
            {"type": "object", "properties": {"kind": {"const": "heading"}, "text": {"type": "string"}, "level": {"type": "integer"}}, "required": ["kind", "text"]},
            {"type": "object", "properties": {"kind": {"const": "callout"}, "tone": {"enum": ["signal", "risk", "neutral"]}, "title": {"type": "string"}, "text": {"type": "string"}}, "required": ["kind", "title", "text"]},
        ]
    },
}


def _coerce_block(raw: dict) -> PageBlock | None:
    kind = raw.get("kind")
    try:
        if kind == "paragraph":
            return ParagraphBlock(**raw)
        if kind == "heading":
            return HeadingBlock(**raw)
        if kind == "callout":
            return CalloutBlock(**raw)
        if kind == "endpoint_table":
            return EndpointTableBlock(**raw)
        if kind == "safety_heatmap":
            return SafetyHeatmapBlock(**raw)
        if kind == "trial_timeline":
            return TrialTimelineBlock(**raw)
        if kind == "evidence_hierarchy":
            return EvidenceHierarchyBlock(**raw)
    except Exception as exc:  # noqa: BLE001
        log.warning("Block coercion failed: %s — %s", exc, raw)
    return None


# Deterministic fallback composers (also used when no Claude key) ----------


def _deterministic_page(
    role_idx: int,
    role: tuple[str, str],
    findings: list[ClinicalFinding],
    citation_index: dict[str, int],
    trials: list[Trial],
    company_name: str,
    all_findings: list[ClinicalFinding],
) -> list[PageBlock]:
    title, _ = role
    blocks: list[PageBlock] = [HeadingBlock(text=title, level=1)]

    if role_idx == 1:
        top = findings[:3]
        risks = summarize_risks(all_findings)
        blocks.append(
            ParagraphBlock(
                text=_exec_summary_text(company_name, all_findings, trials),
                citation_numbers=[
                    citation_index[f.source_doc_id] for f in top if f.source_doc_id in citation_index
                ],
            )
        )
        if top:
            f = top[0]
            blocks.append(
                CalloutBlock(
                    tone="signal",
                    title="Strongest clinical signal",
                    text=_finding_one_liner(f),
                    citation_numbers=[citation_index[f.source_doc_id]] if f.source_doc_id in citation_index else [],
                )
            )
        if risks:
            blocks.append(
                CalloutBlock(
                    tone="risk",
                    title="Top risk surface",
                    text="; ".join(f"{label} ({n})" for label, n in risks[:3]),
                )
            )
        blocks.append(_evidence_hierarchy(all_findings, citation_index))

    elif role_idx == 2:
        blocks.append(_trial_timeline(trials))
        blocks.append(ParagraphBlock(text=_trial_methodology_paragraph(trials)))

    elif role_idx == 3:
        blocks.append(_endpoint_table(findings, citation_index, "Primary + key secondary endpoints"))
        durability = [f for f in findings if f.follow_up_months and f.follow_up_months >= 12]
        if durability:
            blocks.append(
                ParagraphBlock(
                    text=_durability_paragraph(durability),
                    citation_numbers=[
                        citation_index[f.source_doc_id] for f in durability if f.source_doc_id in citation_index
                    ],
                )
            )

    elif role_idx == 4:
        blocks.append(_safety_heatmap(findings, citation_index))
        worst = max(
            findings,
            key=lambda f: _scores(f).safety_concern,
            default=None,
        )
        if worst and _scores(worst).safety_concern >= 0.6:
            blocks.append(
                CalloutBlock(
                    tone="risk",
                    title="Safety signal worth diligence",
                    text=_finding_one_liner(worst),
                    citation_numbers=[citation_index[worst.source_doc_id]] if worst.source_doc_id in citation_index else [],
                )
            )

    elif role_idx == 5:
        for f in findings[:5]:
            blocks.append(
                ParagraphBlock(
                    text=_interpretation_paragraph(f),
                    citation_numbers=[citation_index[f.source_doc_id]] if f.source_doc_id in citation_index else [],
                )
            )

    elif role_idx == 6:
        risks = summarize_risks(all_findings)
        for label, n in risks[:6]:
            blocks.append(
                CalloutBlock(
                    tone="risk",
                    title=label,
                    text=f"Observed in {n} ranked finding(s).",
                )
            )
        # Citations panel is rendered automatically on the last page by the frontend.

    else:
        # extra pages 7..10
        for f in findings[:4]:
            blocks.append(
                ParagraphBlock(
                    text=_finding_one_liner(f),
                    citation_numbers=[citation_index[f.source_doc_id]] if f.source_doc_id in citation_index else [],
                )
            )
    return blocks


def _exec_summary_text(
    company_name: str, findings: list[ClinicalFinding], trials: list[Trial]
) -> str:
    n_findings = len(findings)
    verified = sum(
        1
        for f in findings
        if (f.verification_status == VerificationStatus.VERIFIED.value or f.verification_status == VerificationStatus.VERIFIED)
    )
    n_trials = len(trials)
    phase3 = sum(1 for t in trials if (t.phase == TrialPhase.phase3.value or t.phase == TrialPhase.phase3))
    return (
        f"{company_name}'s clinical evidence base spans {n_trials} trial(s) "
        f"({phase3} late-stage) with {n_findings} material findings; "
        f"{verified} corroborated across ≥2 independent sources. "
        f"Evidence-weighted signal density is driven by the items in the "
        f"endpoint and safety analyses on the following pages."
    )


def _finding_one_liner(f: ClinicalFinding) -> str:
    parts: list[str] = []
    if f.endpoint:
        parts.append(f.endpoint)
    if f.result and f.result.value is not None:
        unit = f.result.units or ""
        parts.append(f"{f.result.value}{unit}")
    if f.result and f.result.p_value is not None:
        parts.append(f"p={f.result.p_value:g}")
    if f.result and f.result.n is not None:
        parts.append(f"n={f.result.n}")
    if not parts:
        return f.description[:240]
    return " — ".join([f.description[:160], ", ".join(parts)])


def _evidence_hierarchy(
    findings: list[ClinicalFinding], citation_index: dict[str, int]
) -> EvidenceHierarchyBlock:
    by_type: dict[str, list[ClinicalFinding]] = {}
    for f in findings:
        key = f.finding_type if isinstance(f.finding_type, str) else f.finding_type.value
        by_type.setdefault(key, []).append(f)
    entries: list[EvidenceHierarchyEntry] = []
    for label, group in by_type.items():
        weight = round(sum(_scores(f).composite() for f in group), 3)
        # use the strongest finding's verification + citation
        strongest = max(group, key=lambda f: _scores(f).composite())
        cit = citation_index.get(strongest.source_doc_id)
        verification = strongest.verification_status
        try:
            v = VerificationStatus(verification if isinstance(verification, str) else verification.value)
        except Exception:  # noqa: BLE001
            v = VerificationStatus.REPORTED
        entries.append(
            EvidenceHierarchyEntry(
                label=label.title(),
                weight=weight,
                verification=v,
                citation_numbers=[cit] if cit else [],
            )
        )
    entries.sort(key=lambda e: e.weight, reverse=True)
    return EvidenceHierarchyBlock(title="Evidence hierarchy by finding type", entries=entries)


def _trial_timeline(trials: list[Trial]) -> TrialTimelineBlock:
    entries = [
        TrialTimelineEntry(
            label=t.title or t.nct_id or t.trial_id,
            phase=TrialPhase(t.phase) if isinstance(t.phase, str) else t.phase,
            start=t.start_date,
            end=t.primary_completion_date,
            status=t.status,
        )
        for t in trials[:10]
    ]
    return TrialTimelineBlock(title="Trial portfolio", entries=entries)


def _trial_methodology_paragraph(trials: list[Trial]) -> str:
    if not trials:
        return "No registered trials identified in public sources."
    rct = sum(1 for t in trials if t.randomized)
    blinded = sum(1 for t in trials if t.blinded)
    placebo = sum(1 for t in trials if t.placebo_controlled)
    enrollments = [t.enrollment for t in trials if t.enrollment]
    avg_n = int(sum(enrollments) / len(enrollments)) if enrollments else 0
    return (
        f"{rct}/{len(trials)} randomized; {blinded}/{len(trials)} blinded; "
        f"{placebo}/{len(trials)} placebo-controlled. "
        f"Mean enrollment per trial: {avg_n}."
    )


def _endpoint_table(
    findings: list[ClinicalFinding], citation_index: dict[str, int], title: str
) -> EndpointTableBlock:
    rows: list[EndpointTableRow] = []
    for f in findings[:10]:
        if not f.endpoint and not f.result:
            continue
        result_str = None
        if f.result:
            if f.result.value is not None:
                result_str = f"{f.result.value}{f.result.units or ''}"
            elif f.result.measure:
                result_str = f.result.measure
        ci = (
            f"[{f.result.ci_low}, {f.result.ci_high}]"
            if f.result and f.result.ci_low is not None and f.result.ci_high is not None
            else None
        )
        cit = citation_index.get(f.source_doc_id)
        rows.append(
            EndpointTableRow(
                endpoint=f.endpoint or "(unspecified)",
                endpoint_type=EndpointType(f.endpoint_type) if isinstance(f.endpoint_type, str) else f.endpoint_type,
                result=result_str,
                p_value=f.result.p_value if f.result else None,
                ci=ci,
                n=f.result.n if f.result else None,
                citation_numbers=[cit] if cit else [],
            )
        )
    return EndpointTableBlock(title=title, rows=rows)


def _durability_paragraph(findings: list[ClinicalFinding]) -> str:
    months = [f.follow_up_months for f in findings if f.follow_up_months]
    if not months:
        return "Durability data not available at this snapshot."
    longest = max(months)
    return f"Longest reported follow-up: {longest} months across {len(months)} finding(s)."


def _safety_heatmap(
    findings: list[ClinicalFinding], citation_index: dict[str, int]
) -> SafetyHeatmapBlock:
    rows: list[SafetyHeatmapRow] = []
    for f in findings[:12]:
        sc = _scores(f).safety_concern
        if sc >= 0.7:
            severity: str = "sae"
        elif sc >= 0.5:
            severity = "severe"
        elif sc >= 0.3:
            severity = "moderate"
        else:
            severity = "mild"
        cit = citation_index.get(f.source_doc_id)
        rows.append(
            SafetyHeatmapRow(
                event=f.endpoint or (f.description[:60] if f.description else "AE"),
                rate_treatment=(f.result.value if f.result and f.result.value is not None else None),
                rate_control=None,
                severity=severity,
                citation_numbers=[cit] if cit else [],
            )
        )
    return SafetyHeatmapBlock(title="Adverse event profile", rows=rows)


def _interpretation_paragraph(f: ClinicalFinding) -> str:
    s = _scores(f)
    bits: list[str] = [_finding_one_liner(f)]
    if s.physician_relevance >= 0.6:
        bits.append("Adoption-relevant given endpoint quality and effect size.")
    if s.commercialization_relevance >= 0.6:
        bits.append("Supports commercialization narrative on clinically familiar endpoints.")
    if s.regulatory_relevance >= 0.7:
        bits.append("Aligns with the endpoint set regulators have historically accepted.")
    return " ".join(bits)


# Public entry point -------------------------------------------------------


def generate_pages(
    *,
    findings: list[ClinicalFinding],
    trials: list[Trial],
    citations: list[Citation],
    company_name: str,
    page_count: int,
    use_llm: bool = True,
) -> list[Page]:
    citation_index = {c.doc_id: c.number for c in citations}
    pages: list[Page] = []

    for idx in range(1, page_count + 1):
        role = PAGE_ROLES.get(idx) or EXTRA_PAGE_ROLES.get(idx)
        if not role:
            continue
        title, instructions = role
        page_findings = _findings_for_page(idx, findings)

        blocks: list[PageBlock] = []
        if use_llm:
            brief = _brief(idx, page_findings, citation_index, company_name)
            raw_blocks = generate_page_blocks(
                system_prompt=SYSTEM_PROMPT,
                page_instructions=instructions,
                brief_json=brief,
                block_schema=_BLOCK_SCHEMA,
            )
            if raw_blocks:
                coerced = [b for b in (_coerce_block(rb) for rb in raw_blocks) if b is not None]
                if coerced:
                    blocks = [HeadingBlock(text=title, level=1), *coerced]

        if not blocks:
            blocks = _deterministic_page(
                idx, role, page_findings, citation_index, trials, company_name, findings
            )

        pages.append(Page(index=idx, title=title, blocks=blocks))
    return pages
