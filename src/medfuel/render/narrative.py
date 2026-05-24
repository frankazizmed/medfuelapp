from __future__ import annotations

from medfuel.llm.base import NarratorLLM
from medfuel.models import RegulatoryEvent, VerifiedClaim
from medfuel.render.layout import LayoutPlan, SectionPlan

_SYSTEM_PROMPT = (
    "You are MedFuel's institutional regulatory editor. You write tight, "
    "decision-dense prose for buy-side diligence. Constraints:\n"
    "- Do not introduce facts that are not present in the supplied claims.\n"
    "- Every sentence must be supportable by at least one supplied citation number.\n"
    "- Respect the per-section word budget; refuse padding.\n"
    "- Use inline citations of the form [n] that map to the supplied citation table.\n"
    "- Prefer dates, agencies, pathways, and concrete regulatory consequences over adjectives.\n"
)


class NarrativeRenderer:
    """Generates institutional-print narrative from a verified-claim layout.

    Drives the configured NarratorLLM with the design's fixed report skeleton.
    The deterministic stub narrator returns the prompt verbatim, so the renderer
    is also useful as a fully-templated report builder when LLMs are disabled.
    """

    def __init__(self, llm: NarratorLLM):
        self._llm = llm

    @property
    def model_id(self) -> str:
        return self._llm.model_id

    async def render(
        self,
        *,
        company_name: str,
        layout: LayoutPlan,
        events: dict[str, RegulatoryEvent],
        claims: dict[str, VerifiedClaim],
        citation_map: dict[str, list[int]],
    ) -> str:
        parts: list[str] = [f"# Regulatory Diligence: {company_name}"]
        for section in layout.sections:
            parts.append(self._format_section_header(section))
            section_claims = [
                claims[cid] for cid in section.claim_ids if cid in claims
            ]
            overflow_claims = [
                claims[cid] for cid in section.overflow_claim_ids if cid in claims
            ]
            table_claims = [
                claims[cid] for cid in section.table_claim_ids if cid in claims
            ]
            if not section_claims and not overflow_claims and not table_claims:
                parts.append("_No verified claims placed in this section for this run._\n")
                continue

            body = await self._render_section(
                section=section,
                section_claims=section_claims,
                overflow_claims=overflow_claims,
                events=events,
                citation_map=citation_map,
            )
            parts.append(body.rstrip() + "\n")
            if table_claims:
                parts.append(self._render_table(table_claims, events, citation_map))

        if layout.adaptive_expansion_triggered:
            parts.append(
                f"\n_Adaptive expansion triggered "
                f"({layout.pages_requested} → {layout.pages_rendered} pages): "
                + "; ".join(layout.expansion_reasons)
                + "._\n"
            )
        return "\n".join(parts)

    @staticmethod
    def _render_table(
        table_claims: list[VerifiedClaim],
        events: dict[str, RegulatoryEvent],
        citation_map: dict[str, list[int]],
    ) -> str:
        # Lower-signal (55-74) claims appear only as a compact supporting table,
        # never in the narrative prose — this is the design's signal-vs-noise
        # rule that mid-tier items get tabulated, not narrated.
        lines = ["\n_Supporting (mid-signal, table only):_"]
        for claim in table_claims:
            event = events.get(claim.event_id)
            if event is None:
                continue
            cites = citation_map.get(claim.claim_id, claim.citation_numbers)
            cite_tag = " " + " ".join(f"[{n}]" for n in cites) if cites else ""
            lines.append(
                f"  - ({event.event_date.isoformat()}) "
                f"{event.agency} {event.event_type.replace('_', ' ')} — "
                f"{event.status}{cite_tag}"
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _format_section_header(section: SectionPlan) -> str:
        b = section.budget
        return (
            f"\n## {section.title}\n"
            f"_Budget: {b.word_min}-{b.word_max} words. {b.objective}. "
            f"Visuals: {b.visuals}._\n"
        )

    async def _render_section(
        self,
        *,
        section: SectionPlan,
        section_claims: list[VerifiedClaim],
        overflow_claims: list[VerifiedClaim],
        events: dict[str, RegulatoryEvent],
        citation_map: dict[str, list[int]],
    ) -> str:
        lines: list[str] = []
        for claim in section_claims + overflow_claims:
            event = events.get(claim.event_id)
            if event is None:
                continue
            cites = citation_map.get(claim.claim_id, claim.citation_numbers)
            cite_tag = " " + " ".join(f"[{n}]" for n in cites) if cites else ""
            lines.append(
                f"- ({event.event_date.isoformat()}) "
                f"{event.agency} {event.event_type.replace('_', ' ')} — "
                f"{event.status}: {event.summary}{cite_tag}"
            )

        prompt = (
            f"sections={section.slug}\n"
            f"objective={section.budget.objective}\n"
            f"word_budget={section.budget.word_min}-{section.budget.word_max}\n"
            f"visuals={section.budget.visuals}\n"
            "claims:\n" + "\n".join(lines)
        )
        return await self._llm.generate(
            system=_SYSTEM_PROMPT,
            prompt=prompt,
            max_tokens=900,
        )
