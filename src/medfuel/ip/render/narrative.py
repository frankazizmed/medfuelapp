"""IP narrative renderer.

Drives the configured NarratorLLM with the 5-page institutional IP
skeleton. Receives structured findings + citation map only — never
raw patent dumps.

In CI / offline mode the renderer leans on the StubNarratorLLM which
echoes the prompt back; tests assert section structure deterministically.
"""

from __future__ import annotations

from medfuel.ip.models import IPFinding
from medfuel.ip.render.layout import IPLayoutPlan, IPSectionPlan
from medfuel.llm.base import NarratorLLM

_SYSTEM_PROMPT = (
    "You are MedFuel's institutional IP diligence editor. You write tight, "
    "decision-dense prose for buy-side life-sciences investors. Constraints:\n"
    "- Do not introduce facts beyond the supplied IP findings.\n"
    "- Every sentence must be supportable by at least one supplied citation [n].\n"
    "- Respect the per-section word budget; refuse padding.\n"
    "- Prefer claim-type, jurisdiction, exclusivity years, and concrete moat or "
    "FTO consequences over adjectives like 'strong' or 'robust'.\n"
    "- Never describe individual patents; reason in patent families.\n"
    "- Skip legal jargon and prosecution-history detail unless materially "
    "altering defensibility, exclusivity, commercialization, FTO, or valuation.\n"
)


class IPNarrativeRenderer:
    def __init__(self, llm: NarratorLLM):
        self._llm = llm

    @property
    def model_id(self) -> str:
        return self._llm.model_id

    async def render(
        self,
        *,
        company_name: str,
        layout: IPLayoutPlan,
        findings: dict[str, IPFinding],
        citation_map: dict[str, list[int]],
    ) -> str:
        parts: list[str] = [f"# IP Diligence: {company_name}"]
        for section in layout.sections:
            parts.append(self._format_section_header(section))
            section_findings = [
                findings[fid] for fid in section.finding_ids if fid in findings
            ]
            overflow_findings = [
                findings[fid] for fid in section.overflow_finding_ids if fid in findings
            ]
            if not section_findings and not overflow_findings:
                parts.append("_No findings placed in this section for this run._\n")
                continue
            body = await self._render_section(
                section=section,
                findings_in=section_findings,
                overflow=overflow_findings,
                citation_map=citation_map,
            )
            parts.append(body.rstrip() + "\n")

        if layout.adaptive_expansion_triggered:
            parts.append(
                f"\n_Adaptive expansion triggered "
                f"({layout.pages_requested} → {layout.pages_rendered} pages): "
                + "; ".join(layout.expansion_reasons)
                + "._\n"
            )
        return "\n".join(parts)

    @staticmethod
    def _format_section_header(section: IPSectionPlan) -> str:
        b = section.budget
        return (
            f"\n## {section.title}\n"
            f"_Budget: {b.word_min}-{b.word_max} words. {b.objective}. "
            f"Visuals: {b.visuals}._\n"
        )

    async def _render_section(
        self,
        *,
        section: IPSectionPlan,
        findings_in: list[IPFinding],
        overflow: list[IPFinding],
        citation_map: dict[str, list[int]],
    ) -> str:
        lines: list[str] = []
        for f in findings_in + overflow:
            cites = citation_map.get(f.finding_id, f.citation_numbers)
            cite_tag = " " + " ".join(f"[{n}]" for n in cites) if cites else ""
            lines.append(
                f"- ({f.verification_state.value}/{f.confidence.value}, "
                f"signal {f.signal_score:.0f}) {f.text}{cite_tag}"
            )
        prompt = (
            f"section={section.slug}\n"
            f"objective={section.budget.objective}\n"
            f"word_budget={section.budget.word_min}-{section.budget.word_max}\n"
            f"visuals={section.budget.visuals}\n"
            "findings:\n" + "\n".join(lines)
        )
        return await self._llm.generate(
            system=_SYSTEM_PROMPT,
            prompt=prompt,
            max_tokens=900,
        )
