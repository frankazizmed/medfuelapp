"""Translate scored families + verification state into IPFindings.

Findings are the atomic unit the renderer prose against — every
sentence in the narrative maps back to a finding (and its citations).
The generator emits 1-5 findings per family across the five sections,
filtered by the signal-vs-noise engine.
"""

from __future__ import annotations

import uuid
from datetime import date

from medfuel.ip.models import (
    FrameworkScores,
    IPConfidence,
    IPFinding,
    IPVerificationState,
    PatentFamily,
)
from medfuel.ip.score.noise import is_low_signal_family
from medfuel.ip.score.signal import compute_signal_score


def build_findings(
    *,
    families: list[PatentFamily],
    scores_by_family: dict[str, FrameworkScores],
    verification_by_family: dict[str, tuple[IPVerificationState, IPConfidence]],
    today: date | None = None,
) -> list[IPFinding]:
    today = today or date.today()
    out: list[IPFinding] = []
    for family in families:
        scores = scores_by_family[family.family_id]
        state, conf = verification_by_family.get(
            family.family_id,
            (IPVerificationState.INFERRED, IPConfidence.LOW),
        )
        if is_low_signal_family(family, scores):
            # Single-line "table-only" finding so the family still shows
            # up on the portfolio matrix without consuming prose budget.
            out.append(
                _finding(
                    family=family,
                    scores=scores,
                    state=state,
                    confidence=conf,
                    category="portfolio",
                    text=_table_only_text(family, scores),
                )
            )
            continue

        out.append(_executive_finding(family, scores, state, conf))
        out.append(_portfolio_finding(family, scores, state, conf))
        out.append(_claims_moat_finding(family, scores, state, conf))
        out.append(_commercial_finding(family, scores, state, conf))
        out.append(_risk_finding(family, scores, state, conf, today=today))
    return out


# --------------------------------------------------------------------------- per-section


def _executive_finding(family, scores, state, confidence) -> IPFinding:
    text = (
        f"{family.representative_title} anchors a {family.dominant_claim_type.value} family "
        f"with a signal score of {compute_signal_score(scores):.0f} "
        f"(moat {scores.moat:.0f}, exclusivity {scores.exclusivity:.0f}). "
        f"Verification: {state.value}, confidence {confidence.value}."
    )
    return _finding(family, scores, state, confidence, "executive", text)


def _portfolio_finding(family, scores, state, confidence) -> IPFinding:
    jurisdiction_count = len(family.coverage)
    members = len(family.members)
    extensions = family.continuation_count + family.divisional_count + family.cip_count
    text = (
        f"{members} members across {jurisdiction_count} jurisdictions; "
        f"{extensions} active continuation-type filings sustain lifecycle flexibility. "
        f"Portfolio quality score {scores.portfolio_quality:.0f}."
    )
    return _finding(family, scores, state, confidence, "portfolio", text)


def _claims_moat_finding(family, scores, state, confidence) -> IPFinding:
    types: list[str] = []
    if family.has_composition_claims:
        types.append("composition")
    if family.has_method_claims:
        types.append("method")
    if family.has_device_claims:
        types.append("device")
    type_blob = ", ".join(types) or "narrow technical"
    text = (
        f"Independent claims span {type_blob} coverage. "
        f"Claim strength {scores.claim_strength:.0f}, moat {scores.moat:.0f}, "
        f"differentiation {scores.differentiation:.0f}."
    )
    return _finding(family, scores, state, confidence, "claims_moat", text)


def _commercial_finding(family, scores, state, confidence) -> IPFinding:
    text = (
        f"Commercialization protection score {scores.commercialization:.0f}; "
        f"forward citations to date: {family.forward_citation_total}. "
    )
    if family.has_composition_claims and family.has_device_claims:
        text += "Composition + device coverage indicates product-level moat."
    elif family.has_composition_claims:
        text += "Composition-only coverage; device/method extensions could broaden lock-in."
    elif family.has_software_only_claims:
        text += "Software-centric claim set; design-around exposure is elevated."
    else:
        text += "Coverage is process- or method-centric; suitable for workflow defensibility."
    return _finding(family, scores, state, confidence, "commercial_competitive", text)


def _risk_finding(family, scores, state, confidence, *, today: date) -> IPFinding:
    if family.latest_expiration_estimate:
        years = (family.latest_expiration_estimate - today).days / 365.25
        excl_blob = f"{years:.1f} year(s) of estimated exclusivity remain"
    else:
        excl_blob = "exclusivity horizon unknown"
    text = (
        f"FTO risk score {scores.fto_risk:.0f} "
        f"(higher = less risk); {excl_blob}."
    )
    return _finding(family, scores, state, confidence, "risk_fto", text)


def _table_only_text(family, scores) -> str:
    return (
        f"{family.representative_title} — table-only "
        f"(signal {compute_signal_score(scores):.0f}, "
        f"{len(family.members)} members)."
    )


def _finding(family, scores, state, confidence, category, text) -> IPFinding:
    return IPFinding(
        finding_id=f"ipf_{uuid.uuid4().hex[:12]}",
        family_id=family.family_id,
        category=category,  # type: ignore[arg-type]
        text=text,
        verification_state=state,
        confidence=confidence,
        signal_score=compute_signal_score(scores),
        framework_scores=scores,
        source_doc_ids=list(
            {sid for m in family.members for sid in m.source_doc_ids}
        ),
        citation_numbers=[],
    )
