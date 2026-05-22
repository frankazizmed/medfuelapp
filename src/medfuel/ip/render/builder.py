"""IP report builder.

End-to-end: load persisted families + adjacent IP signals → score
frameworks → build findings → build citations → render narrative →
persist an IPReportRunRow.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from medfuel.db.orm import CompanyRow, SourceDocumentRow
from medfuel.ip.db_orm import (
    IPFindingRow,
    IPPatentFamilyRow,
    IPPatentRecordRow,
    IPProceedingRow,
    IPReportRunRow,
)
from medfuel.ip.models import (
    ClaimType,
    FamilyJurisdictionCoverage,
    FilingKind,
    FrameworkScores,
    IPConfidence,
    IPFinding,
    IPReportPlan,
    IPSourceType,
    IPVerificationState,
    LegalStatus,
    PatentClaim,
    PatentFamily,
    PatentRecord,
)
from medfuel.ip.render.citations import build_ip_citation_table
from medfuel.ip.render.findings import build_findings
from medfuel.ip.render.layout import IPLayoutPlan, plan_ip_layout
from medfuel.ip.render.narrative import IPNarrativeRenderer
from medfuel.ip.score.frameworks import score_all_frameworks
from medfuel.ip.score.signal import compute_signal_score, family_table_summary
from medfuel.ip.verify import IPVerifier
from medfuel.llm.factory import get_extractor_llm, get_narrator_llm
from medfuel.models.schemas import SourceType


class IPReportBuilder:
    def __init__(self, session: Session):
        self.session = session
        self._narrator = get_narrator_llm()
        self._extractor_model_id = get_extractor_llm().model_id

    async def build(
        self,
        *,
        company_id: str,
        job_id: str | None,
        plan: IPReportPlan,
    ) -> IPReportRunRow:
        families = self._load_families(company_id)
        if not families:
            return self._persist_empty(company_id, job_id, plan)

        proceeding_counts = self._proceeding_counts(company_id)
        assignments_by_patent = self._assignments_by_patent(company_id)

        # Score frameworks per family.
        scores_by_family: dict[str, FrameworkScores] = {}
        for family in families:
            scores_by_family[family.family_id] = score_all_frameworks(
                family,
                blocking_patent_count=0,
                active_litigation_count=proceeding_counts.get(family.family_id, {}).get(
                    "litigation", 0
                ),
                ptab_challenge_count=proceeding_counts.get(family.family_id, {}).get(
                    "ptab", 0
                ),
                today=date.today(),
            )

        # Verify per family.
        doc_ranks, primary_sources = self._source_metadata(families)
        verifier = IPVerifier()
        verification_by_family = verifier.verify(
            families=families,
            doc_ranks=doc_ranks,
            primary_sources=primary_sources,
            assignments_by_patent=assignments_by_patent,
        )

        # Build findings.
        findings = build_findings(
            families=families,
            scores_by_family=scores_by_family,
            verification_by_family=verification_by_family,
        )

        # Persist scores onto the family rows (audit / re-render).
        self._write_back_family_scores(families, scores_by_family)

        # Lay out.
        layout = plan_ip_layout(
            findings=findings,
            requested_pages=plan.requested_pages,
            soft_max_pages=plan.soft_max_pages,
            hard_max_pages=plan.hard_max_pages,
        )

        report_id = f"iprpt_{uuid.uuid4().hex[:12]}"
        citations, citation_map = build_ip_citation_table(
            session=self.session, report_id=report_id, findings=findings
        )

        # Persist findings.
        self._persist_findings(company_id, job_id, findings, citation_map)

        company = self.session.get(CompanyRow, company_id)
        company_name = company.legal_name if company else company_id

        renderer = IPNarrativeRenderer(self._narrator)
        narrative = await renderer.render(
            company_name=company_name,
            layout=layout,
            findings={f.finding_id: f for f in findings},
            citation_map=citation_map,
        )

        portfolio_summary = self._portfolio_summary(families, scores_by_family)
        confidence_summary = self._confidence_summary(findings)

        row = IPReportRunRow(
            report_id=report_id,
            company_id=company_id,
            job_id=job_id,
            pages_requested=layout.pages_requested,
            pages_rendered=layout.pages_rendered,
            soft_max_pages=layout.soft_max_pages,
            hard_max_pages=layout.hard_max_pages,
            adaptive_expansion_triggered=layout.adaptive_expansion_triggered,
            layout_plan=self._layout_to_dict(layout, citations),
            narrative_text=narrative,
            confidence_summary=confidence_summary,
            portfolio_summary=portfolio_summary,
            status="complete",
            narrative_model=self._narrator.model_id,
            extraction_model=self._extractor_model_id,
        )
        self.session.add(row)
        self.session.flush()
        return row

    # ----------------------------------------------------------- loading helpers
    def _load_families(self, company_id: str) -> list[PatentFamily]:
        family_rows = (
            self.session.query(IPPatentFamilyRow)
            .filter(IPPatentFamilyRow.company_id == company_id)
            .all()
        )
        if not family_rows:
            return []
        patent_rows = (
            self.session.query(IPPatentRecordRow)
            .filter(IPPatentRecordRow.company_id == company_id)
            .all()
        )
        patents_by_family: dict[str, list[PatentRecord]] = {}
        for r in patent_rows:
            patents_by_family.setdefault(r.family_id or "", []).append(_row_to_patent(r))

        out: list[PatentFamily] = []
        for fr in family_rows:
            members = patents_by_family.get(fr.family_id, [])
            out.append(
                PatentFamily(
                    family_id=fr.family_id,
                    representative_title=fr.representative_title,
                    earliest_priority_date=fr.earliest_priority_date,
                    latest_expiration_estimate=fr.latest_expiration_estimate,
                    members=members,
                    coverage=[
                        FamilyJurisdictionCoverage(**c) for c in (fr.coverage_payload or [])
                    ],
                    continuation_count=fr.continuation_count,
                    divisional_count=fr.divisional_count,
                    cip_count=fr.cip_count,
                    independent_claims=[
                        PatentClaim(**c) for c in (fr.independent_claims_payload or [])
                    ],
                    dominant_claim_type=ClaimType(fr.dominant_claim_type),
                    forward_citation_total=fr.forward_citation_total,
                    has_composition_claims=fr.has_composition_claims,
                    has_method_claims=fr.has_method_claims,
                    has_device_claims=fr.has_device_claims,
                    has_software_only_claims=fr.has_software_only_claims,
                    assignees=list(fr.assignees or []),
                    notes=list(fr.notes or []),
                )
            )
        return out

    def _proceeding_counts(self, company_id: str) -> dict[str, dict[str, int]]:
        rows = (
            self.session.query(IPProceedingRow)
            .filter(IPProceedingRow.company_id == company_id)
            .all()
        )
        out: dict[str, dict[str, int]] = {}
        # Attribute proceedings to families via the patent_or_application string
        # match against family member publication/application numbers.
        family_rows = (
            self.session.query(IPPatentFamilyRow)
            .filter(IPPatentFamilyRow.company_id == company_id)
            .all()
        )
        patent_to_family: dict[str, str] = {}
        for fr in family_rows:
            for pid in fr.member_patent_ids or []:
                patent_to_family[pid] = fr.family_id
        member_rows = (
            self.session.query(IPPatentRecordRow)
            .filter(IPPatentRecordRow.company_id == company_id)
            .all()
        )
        pub_to_family: dict[str, str] = {}
        for m in member_rows:
            for key in (m.publication_number, m.application_number):
                if key and m.family_id:
                    pub_to_family[key] = m.family_id
        for r in rows:
            family_id = pub_to_family.get(r.patent_or_application or "")
            if family_id is None:
                continue
            bucket = out.setdefault(family_id, {"litigation": 0, "ptab": 0, "assignment": 0})
            bucket[r.kind] = bucket.get(r.kind, 0) + 1
        return out

    def _assignments_by_patent(self, company_id: str) -> dict[str, list[str]]:
        rows = (
            self.session.query(IPProceedingRow)
            .filter(
                IPProceedingRow.company_id == company_id,
                IPProceedingRow.kind == "assignment",
            )
            .all()
        )
        out: dict[str, list[str]] = {}
        for r in rows:
            key = r.patent_or_application or ""
            out.setdefault(key, []).append(r.proceeding_id)
        return out

    def _source_metadata(
        self, families: list[PatentFamily]
    ) -> tuple[dict[str, int], dict[str, SourceType]]:
        ids = sorted({sid for f in families for m in f.members for sid in m.source_doc_ids})
        if not ids:
            return {}, {}
        rows = (
            self.session.query(SourceDocumentRow)
            .filter(SourceDocumentRow.source_doc_id.in_(ids))
            .all()
        )
        ranks = {r.source_doc_id: r.official_rank for r in rows}
        sources = {r.source_doc_id: SourceType(r.source_type) for r in rows}
        return ranks, sources

    # ----------------------------------------------------------- write helpers
    def _write_back_family_scores(
        self,
        families: list[PatentFamily],
        scores: dict[str, FrameworkScores],
    ) -> None:
        rows = {
            r.family_id: r
            for r in self.session.query(IPPatentFamilyRow)
            .filter(IPPatentFamilyRow.family_id.in_([f.family_id for f in families]))
            .all()
        }
        for family in families:
            row = rows.get(family.family_id)
            if row is None:
                continue
            row.framework_scores = scores[family.family_id].model_dump(mode="json")
            row.signal_score = compute_signal_score(scores[family.family_id])
        self.session.flush()

    def _persist_findings(
        self,
        company_id: str,
        job_id: str | None,
        findings: list[IPFinding],
        citation_map: dict[str, list[int]],
    ) -> None:
        for f in findings:
            f.citation_numbers = citation_map.get(f.finding_id, [])
            self.session.add(
                IPFindingRow(
                    finding_id=f.finding_id,
                    company_id=company_id,
                    job_id=job_id,
                    family_id=f.family_id,
                    category=f.category,
                    text=f.text,
                    verification_state=f.verification_state.value,
                    confidence=f.confidence.value,
                    signal_score=f.signal_score,
                    framework_scores=f.framework_scores.model_dump(mode="json"),
                    source_doc_ids=f.source_doc_ids,
                    citation_numbers=f.citation_numbers,
                )
            )
        self.session.flush()

    # ----------------------------------------------------------- summary builders
    @staticmethod
    def _portfolio_summary(
        families: list[PatentFamily], scores: dict[str, FrameworkScores]
    ) -> dict[str, Any]:
        rows = [
            family_table_summary(f, scores[f.family_id])
            for f in sorted(
                families,
                key=lambda f: compute_signal_score(scores[f.family_id]),
                reverse=True,
            )
        ]
        return {
            "family_count": len(families),
            "patent_member_count": sum(len(f.members) for f in families),
            "top_families": rows[:10],
        }

    @staticmethod
    def _confidence_summary(findings: list[IPFinding]) -> dict[str, int]:
        counter: Counter[str] = Counter(f.confidence.value for f in findings)
        return {
            "high": counter["high"],
            "medium": counter["medium"],
            "low": counter["low"],
        }

    @staticmethod
    def _layout_to_dict(layout: IPLayoutPlan, citations) -> dict[str, Any]:
        return {
            "pages_requested": layout.pages_requested,
            "pages_rendered": layout.pages_rendered,
            "soft_max_pages": layout.soft_max_pages,
            "hard_max_pages": layout.hard_max_pages,
            "adaptive_expansion_triggered": layout.adaptive_expansion_triggered,
            "expansion_reasons": layout.expansion_reasons,
            "omitted_high_signal_share": layout.omitted_high_signal_share,
            "omitted_critical_count": layout.omitted_critical_count,
            "sections": [
                {
                    "slug": s.slug,
                    "title": s.title,
                    "word_min": s.budget.word_min,
                    "word_max": s.budget.word_max,
                    "finding_ids": s.finding_ids,
                    "overflow_finding_ids": s.overflow_finding_ids,
                }
                for s in layout.sections
            ],
            "citations": [
                {
                    "n": c.inline_number,
                    "finding_id": c.finding_id,
                    "source_doc_id": c.source_doc_id,
                    "url": c.url,
                    "locator": c.locator,
                    "source_confidence": c.source_confidence,
                    "evidence_kind": c.evidence_kind,
                }
                for c in citations
            ],
        }

    def _persist_empty(
        self,
        company_id: str,
        job_id: str | None,
        plan: IPReportPlan,
    ) -> IPReportRunRow:
        report_id = f"iprpt_{uuid.uuid4().hex[:12]}"
        row = IPReportRunRow(
            report_id=report_id,
            company_id=company_id,
            job_id=job_id,
            pages_requested=plan.requested_pages,
            pages_rendered=plan.requested_pages,
            soft_max_pages=plan.soft_max_pages,
            hard_max_pages=plan.hard_max_pages,
            adaptive_expansion_triggered=False,
            layout_plan={"sections": [], "citations": [], "note": "no patent families discovered"},
            narrative_text="# IP Diligence\n\n_No patent families discovered for this company._\n",
            confidence_summary={"high": 0, "medium": 0, "low": 0},
            portfolio_summary={"family_count": 0, "patent_member_count": 0, "top_families": []},
            status="complete_empty",
            narrative_model=self._narrator.model_id,
            extraction_model=self._extractor_model_id,
        )
        self.session.add(row)
        self.session.flush()
        return row


def _row_to_patent(row: IPPatentRecordRow) -> PatentRecord:
    return PatentRecord(
        patent_id=row.patent_id,
        publication_number=row.publication_number,
        application_number=row.application_number,
        title=row.title,
        jurisdiction=row.jurisdiction,
        kind=FilingKind(row.kind),
        filing_date=row.filing_date,
        priority_date=row.priority_date,
        publication_date=row.publication_date,
        grant_date=row.grant_date,
        expiration_estimate=row.expiration_estimate,
        legal_status=LegalStatus(row.legal_status),
        assignees=list(row.assignees or []),
        inventors=list(row.inventors or []),
        family_id=row.family_id,
        parent_publication_numbers=list(row.parent_publication_numbers or []),
        cpc_codes=list(row.cpc_codes or []),
        forward_citations=row.forward_citations,
        backward_citations=row.backward_citations,
        independent_claim_count=row.independent_claim_count,
        dependent_claim_count=row.dependent_claim_count,
        claims=[PatentClaim(**c) for c in (row.claims_payload or [])],
        source_doc_ids=list(row.source_doc_ids or []),
        primary_source=IPSourceType(row.primary_source),
    )


__all__ = [
    "IPConfidence",
    "IPReportBuilder",
    "IPVerificationState",
]
