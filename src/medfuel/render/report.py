from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from medfuel.db.orm import (
    ClaimRow,
    CompanyRow,
    RegulatoryEventRow,
    ReportRunRow,
    SourceDocumentRow,
)
from medfuel.llm.factory import get_extractor_llm, get_narrator_llm
from medfuel.models import (
    Confidence,
    RegulatoryEvent,
    ReportPlan,
    VerificationState,
    VerifiedClaim,
)
from medfuel.render.layout import plan_layout
from medfuel.render.narrative import NarrativeRenderer
from medfuel.score.noise import filter_claims
from medfuel.verify.citations import build_citation_table

log = logging.getLogger(__name__)


class CitationResolveError(RuntimeError):
    """Raised when a placed claim cannot resolve to at least one citation."""


class ReportBuilder:
    """End-to-end Phase 3: layout → citations → narrative → persisted report."""

    def __init__(self, session: Session):
        self.session = session
        self._narrator = get_narrator_llm()
        # Capture the extractor model id only for audit on the report row.
        self._extractor_model_id = get_extractor_llm().model_id

    async def build(
        self,
        *,
        company_id: str,
        job_id: str | None,
        plan: ReportPlan,
    ) -> ReportRunRow:
        events_rows = (
            self.session.query(RegulatoryEventRow)
            .filter(RegulatoryEventRow.company_id == company_id)
            .all()
        )
        events = [self._to_event(r) for r in events_rows]
        event_ids = [e.event_id for e in events]
        claims_rows = (
            self.session.query(ClaimRow)
            .filter(ClaimRow.event_id.in_(event_ids))
            .all()
            if event_ids
            else []
        )
        claims = [self._to_claim(r) for r in claims_rows]

        # Signal-vs-noise gate: enforce threshold bands + fluff-elimination
        # rules BEFORE layout so low-signal, stale, uncited, duplicate, or
        # company-dominated claims never reach the narrative.
        doc_ranks = self._doc_ranks(claims)
        noise = filter_claims(events=events, claims=claims, doc_ranks=doc_ranks)
        kept_ids = noise.kept_claim_ids()
        kept_claims = [c for c in claims if c.claim_id in kept_ids]

        layout = plan_layout(
            events=events,
            claims=kept_claims,
            requested_pages=plan.requested_pages,
            max_pages=plan.max_pages,
            table_only_ids=set(noise.table_claim_ids),
        )

        report_id = f"rpt_{uuid.uuid4().hex[:12]}"
        # Only the claims that survived the noise gate get citations.
        citations, citation_map = build_citation_table(
            session=self.session,
            report_id=report_id,
            claims=kept_claims,
        )
        # Persist the citation number assignment back onto the claim rows so
        # subsequent rerenders inherit the same numbering.
        self._write_back_citations(claims_rows, citation_map)
        # Invariant: every claim the layout placed must resolve to at least one
        # citation. Violations indicate a regression in the extraction → render
        # chain and are unsafe to ship.
        self._assert_citations_resolve(layout=layout, citation_map=citation_map)

        company = self.session.get(CompanyRow, company_id)
        company_name = company.legal_name if company else company_id

        renderer = NarrativeRenderer(self._narrator)
        narrative = await renderer.render(
            company_name=company_name,
            layout=layout,
            events={e.event_id: e for e in events},
            claims={c.claim_id: c for c in kept_claims},
            citation_map=citation_map,
        )

        confidence_summary = self._summarize_confidence(kept_claims)

        row = ReportRunRow(
            report_id=report_id,
            company_id=company_id,
            job_id=job_id,
            pages_requested=layout.pages_requested,
            pages_rendered=layout.pages_rendered,
            adaptive_expansion_triggered=layout.adaptive_expansion_triggered,
            layout_plan=self._layout_to_dict(layout, citations, noise),
            narrative_text=narrative,
            confidence_summary=confidence_summary,
            status="complete",
            narrative_model=self._narrator.model_id,
            extraction_model=self._extractor_model_id,
        )
        self.session.add(row)
        self.session.flush()
        return row

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _to_event(row: RegulatoryEventRow) -> RegulatoryEvent:
        return RegulatoryEvent(
            event_id=row.event_id,
            company_id=row.company_id,
            asset_id=row.asset_id,
            agency=row.agency,
            jurisdiction=row.jurisdiction,
            event_type=row.event_type,  # type: ignore[arg-type]
            status=row.status,
            event_date=row.event_date if isinstance(row.event_date, date) else date.fromisoformat(str(row.event_date)),
            summary=row.summary,
            investor_importance=row.investor_importance,
            evidence_strength=row.evidence_strength,
            source_doc_ids=list(row.source_doc_ids or []),
        )

    @staticmethod
    def _to_claim(row: ClaimRow) -> VerifiedClaim:
        return VerifiedClaim(
            claim_id=row.claim_id,
            event_id=row.event_id,
            text=row.text,
            verification_state=VerificationState(row.verification_state),
            confidence=Confidence(row.confidence),
            source_doc_ids=list(row.source_doc_ids or []),
            citation_numbers=list(row.citation_numbers or []),
            signal_score=row.signal_score,
        )

    def _doc_ranks(self, claims: list[VerifiedClaim]) -> dict[str, int]:
        doc_ids = sorted({sid for c in claims for sid in c.source_doc_ids})
        if not doc_ids:
            return {}
        rows = (
            self.session.query(
                SourceDocumentRow.source_doc_id, SourceDocumentRow.official_rank
            )
            .filter(SourceDocumentRow.source_doc_id.in_(doc_ids))
            .all()
        )
        return {sid: rank for sid, rank in rows}

    def _write_back_citations(
        self,
        rows: list[ClaimRow],
        citation_map: dict[str, list[int]],
    ) -> None:
        by_id = {r.claim_id: r for r in rows}
        for claim_id, nums in citation_map.items():
            row = by_id.get(claim_id)
            if row is None:
                continue
            row.citation_numbers = nums
        self.session.flush()

    @staticmethod
    def _assert_citations_resolve(*, layout, citation_map: dict[str, list[int]]) -> None:
        unresolved: list[str] = []
        for section in layout.sections:
            placed = section.claim_ids + section.overflow_claim_ids + section.table_claim_ids
            for claim_id in placed:
                if not citation_map.get(claim_id):
                    unresolved.append(claim_id)
        if unresolved:
            raise CitationResolveError(
                f"{len(unresolved)} placed claims have no resolved citations: "
                + ", ".join(unresolved[:5])
                + ("..." if len(unresolved) > 5 else "")
            )

    @staticmethod
    def _summarize_confidence(claims: list[VerifiedClaim]) -> dict[str, int]:
        counter: Counter[str] = Counter(c.confidence.value for c in claims)
        return {"high": counter["high"], "medium": counter["medium"], "low": counter["low"]}

    @staticmethod
    def _layout_to_dict(layout, citations, noise) -> dict[str, Any]:
        return {
            "pages_requested": layout.pages_requested,
            "pages_rendered": layout.pages_rendered,
            "max_pages": layout.max_pages,
            "adaptive_expansion_triggered": layout.adaptive_expansion_triggered,
            "expansion_reasons": layout.expansion_reasons,
            "omitted_critical_count": layout.omitted_critical_count,
            "omitted_high_signal_share": layout.omitted_high_signal_share,
            "noise": noise.report(),
            "sections": [
                {
                    "slug": s.slug,
                    "title": s.title,
                    "word_min": s.budget.word_min,
                    "word_max": s.budget.word_max,
                    "claim_ids": s.claim_ids,
                    "overflow_claim_ids": s.overflow_claim_ids,
                    "table_claim_ids": s.table_claim_ids,
                }
                for s in layout.sections
            ],
            "citations": [
                {
                    "n": cit.inline_number,
                    "claim_id": cit.claim_id,
                    "source_doc_id": cit.source_doc_id,
                    "url": cit.url,
                    "locator": cit.locator,
                    "source_confidence": cit.source_confidence,
                }
                for cit in citations
            ],
        }
