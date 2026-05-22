"""IP extraction orchestrator.

Reads source documents from the registry, runs the rule-based IP
extractor, builds patent families, and persists patents + families to
the IP tables. Adjacent IP signals (PTAB, litigation, assignments)
land in ip_proceedings for the verifier to consume.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from medfuel.db.orm import ExtractionRow, SourceDocumentRow
from medfuel.ip.db_orm import (
    IPPatentFamilyRow,
    IPPatentRecordRow,
    IPProceedingRow,
)
from medfuel.ip.extract.family_builder import build_families
from medfuel.ip.extract.patent_rules import RuleBasedIPExtractor
from medfuel.ip.models import (
    AssignmentEvent,
    LitigationRecord,
    PatentFamily,
    PatentRecord,
    PTABProceeding,
)
from medfuel.models import RawSourceRecord, SourceType

log = logging.getLogger(__name__)

# Source types the IP extractor cares about. PUBMED, FDA, etc. flow
# through the regulatory pipeline instead.
_IP_SOURCES: set[SourceType] = {
    SourceType.USPTO,
    SourceType.PATENTSVIEW,
    SourceType.GOOGLE_PATENTS,
    SourceType.EPO,
    SourceType.WIPO,
    SourceType.USPTO_ASSIGNMENT,
    SourceType.PTAB,
    SourceType.LITIGATION,
    SourceType.SEC_IP,
    SourceType.COMPANY_IP,
}


@dataclass
class IPExtractionResult:
    patents: list[PatentRecord] = field(default_factory=list)
    families: list[PatentFamily] = field(default_factory=list)
    proceedings: list[PTABProceeding] = field(default_factory=list)
    litigations: list[LitigationRecord] = field(default_factory=list)
    assignments: list[AssignmentEvent] = field(default_factory=list)


class IPExtractionOrchestrator:
    def __init__(self, extractor: RuleBasedIPExtractor | None = None):
        self._extractor = extractor or RuleBasedIPExtractor()

    def run(
        self,
        *,
        session: Session,
        company_id: str,
        job_id: str | None,
    ) -> IPExtractionResult:
        docs = (
            session.query(SourceDocumentRow)
            .filter(
                SourceDocumentRow.company_id == company_id,
                SourceDocumentRow.source_type.in_({s.value for s in _IP_SOURCES}),
            )
            .all()
        )
        if not docs:
            return IPExtractionResult()

        result = IPExtractionResult()
        patents_by_id: dict[str, PatentRecord] = {}
        for doc in docs:
            record = _to_record(doc)
            try:
                patent = self._extractor.extract_patent(
                    source_doc_id=doc.source_doc_id, record=record
                )
                if patent is not None:
                    existing = patents_by_id.get(patent.patent_id)
                    if existing is None:
                        patents_by_id[patent.patent_id] = patent
                    else:
                        _merge_patents(existing, patent)
                proc = self._extractor.extract_proceeding(
                    source_doc_id=doc.source_doc_id, record=record
                )
                if proc is not None:
                    result.proceedings.append(proc)
                lit = self._extractor.extract_litigation(
                    source_doc_id=doc.source_doc_id, record=record
                )
                if lit is not None:
                    result.litigations.append(lit)
                asg = self._extractor.extract_assignment(
                    source_doc_id=doc.source_doc_id, record=record
                )
                if asg is not None:
                    result.assignments.append(asg)
            except Exception:  # noqa: BLE001
                log.warning("ip extractor failed for %s", doc.source_doc_id, exc_info=True)

        result.patents = list(patents_by_id.values())
        result.families = build_families(result.patents)
        self._persist(session, company_id, job_id, result)
        return result

    # ------------------------------------------------------------------- persist
    def _persist(
        self,
        session: Session,
        company_id: str,
        job_id: str | None,
        result: IPExtractionResult,
    ) -> None:
        session.add(
            ExtractionRow(
                extraction_id=f"ext_{uuid.uuid4().hex[:12]}",
                job_id=job_id,
                source_doc_id=result.patents[0].source_doc_ids[0]
                if result.patents and result.patents[0].source_doc_ids else "ip_aggregate",
                extractor=self._extractor.name,
                payload={
                    "patents": [p.model_dump(mode="json") for p in result.patents],
                    "families": [f.family_id for f in result.families],
                    "proceedings": [p.model_dump(mode="json") for p in result.proceedings],
                    "litigations": [lit.model_dump(mode="json") for lit in result.litigations],
                    "assignments": [a.model_dump(mode="json") for a in result.assignments],
                },
            )
        ) if result.patents else None

        for family in result.families:
            session.add(
                IPPatentFamilyRow(
                    family_id=family.family_id,
                    company_id=company_id,
                    job_id=job_id,
                    representative_title=family.representative_title,
                    earliest_priority_date=family.earliest_priority_date,
                    latest_expiration_estimate=family.latest_expiration_estimate,
                    coverage_payload=[c.model_dump(mode="json") for c in family.coverage],
                    member_patent_ids=[m.patent_id for m in family.members],
                    continuation_count=family.continuation_count,
                    divisional_count=family.divisional_count,
                    cip_count=family.cip_count,
                    independent_claims_payload=[
                        c.model_dump(mode="json") for c in family.independent_claims
                    ],
                    dominant_claim_type=family.dominant_claim_type.value,
                    forward_citation_total=family.forward_citation_total,
                    has_composition_claims=family.has_composition_claims,
                    has_method_claims=family.has_method_claims,
                    has_device_claims=family.has_device_claims,
                    has_software_only_claims=family.has_software_only_claims,
                    assignees=family.assignees,
                    notes=family.notes,
                )
            )
        for patent in result.patents:
            session.add(
                IPPatentRecordRow(
                    patent_id=patent.patent_id,
                    company_id=company_id,
                    job_id=job_id,
                    family_id=patent.family_id,
                    publication_number=patent.publication_number,
                    application_number=patent.application_number,
                    title=patent.title,
                    jurisdiction=patent.jurisdiction,
                    kind=patent.kind.value,
                    filing_date=patent.filing_date,
                    priority_date=patent.priority_date,
                    publication_date=patent.publication_date,
                    grant_date=patent.grant_date,
                    expiration_estimate=patent.expiration_estimate,
                    legal_status=patent.legal_status.value,
                    assignees=patent.assignees,
                    inventors=patent.inventors,
                    parent_publication_numbers=patent.parent_publication_numbers,
                    cpc_codes=patent.cpc_codes,
                    forward_citations=patent.forward_citations,
                    backward_citations=patent.backward_citations,
                    independent_claim_count=patent.independent_claim_count,
                    dependent_claim_count=patent.dependent_claim_count,
                    claims_payload=[c.model_dump(mode="json") for c in patent.claims],
                    source_doc_ids=patent.source_doc_ids,
                    primary_source=patent.primary_source.value,
                )
            )

        for proc in result.proceedings:
            session.add(
                IPProceedingRow(
                    proceeding_id=f"prc_{uuid.uuid4().hex[:12]}",
                    company_id=company_id,
                    job_id=job_id,
                    kind="ptab",
                    patent_or_application=proc.patent_number,
                    counterparty=proc.petitioner,
                    filing_date=proc.filing_date,
                    status=proc.status,
                    outcome=proc.outcome,
                    payload=proc.model_dump(mode="json"),
                    source_doc_id=proc.source_doc_id,
                )
            )
        for lit in result.litigations:
            session.add(
                IPProceedingRow(
                    proceeding_id=f"prc_{uuid.uuid4().hex[:12]}",
                    company_id=company_id,
                    job_id=job_id,
                    kind="litigation",
                    patent_or_application=",".join(lit.patent_numbers) or None,
                    counterparty=",".join(lit.plaintiffs + lit.defendants) or None,
                    filing_date=lit.filing_date,
                    status=lit.status,
                    outcome=None,
                    payload=lit.model_dump(mode="json"),
                    source_doc_id=lit.source_doc_id,
                )
            )
        for asg in result.assignments:
            session.add(
                IPProceedingRow(
                    proceeding_id=f"prc_{uuid.uuid4().hex[:12]}",
                    company_id=company_id,
                    job_id=job_id,
                    kind="assignment",
                    patent_or_application=asg.patent_or_application,
                    counterparty=asg.assignee,
                    filing_date=asg.recorded_date,
                    status=asg.nature,
                    outcome=None,
                    payload=asg.model_dump(mode="json"),
                    source_doc_id=asg.source_doc_id,
                )
            )
        session.flush()


def _merge_patents(existing: PatentRecord, incoming: PatentRecord) -> None:
    """Merge two extractions of the same patent in place.

    Aggregator-only fields (claims, citations) overwrite when richer;
    provenance accumulates so all citing docs stay attached.
    """
    for sid in incoming.source_doc_ids:
        if sid not in existing.source_doc_ids:
            existing.source_doc_ids.append(sid)
    for a in incoming.assignees:
        if a not in existing.assignees:
            existing.assignees.append(a)
    for inv in incoming.inventors:
        if inv not in existing.inventors:
            existing.inventors.append(inv)
    for cpc in incoming.cpc_codes:
        if cpc not in existing.cpc_codes:
            existing.cpc_codes.append(cpc)
    # Prefer the richer claims set when one extractor produced none.
    if not existing.claims and incoming.claims:
        existing.claims = incoming.claims
        existing.independent_claim_count = incoming.independent_claim_count
        existing.dependent_claim_count = incoming.dependent_claim_count
    if incoming.forward_citations > existing.forward_citations:
        existing.forward_citations = incoming.forward_citations
    if incoming.backward_citations > existing.backward_citations:
        existing.backward_citations = incoming.backward_citations
    if existing.priority_date is None and incoming.priority_date is not None:
        existing.priority_date = incoming.priority_date
    if existing.filing_date is None and incoming.filing_date is not None:
        existing.filing_date = incoming.filing_date
    if existing.grant_date is None and incoming.grant_date is not None:
        existing.grant_date = incoming.grant_date
    if existing.expiration_estimate is None and incoming.expiration_estimate is not None:
        existing.expiration_estimate = incoming.expiration_estimate


def _to_record(doc: SourceDocumentRow) -> RawSourceRecord:
    return RawSourceRecord(
        source_type=SourceType(doc.source_type),
        jurisdiction=doc.jurisdiction,
        url=doc.url,
        title=doc.title,
        payload=doc.payload or {},
        published_at=doc.published_at,
        retrieved_at=doc.retrieved_at,
        page_locator=doc.page_locator,
        external_id=doc.external_id,
        content_hash=doc.content_hash,
        official_rank=doc.official_rank,
    )
