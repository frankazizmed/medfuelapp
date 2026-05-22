"""IP intelligence engine REST surface.

Endpoints mirror the regulatory routes (jobs, status, report, narrative,
citations, rerender) but mount under /v1/ip and operate on IP-side
artefacts. The /ip-extract, /ip-signal-rank, /ip-layout endpoints from
the spec are implemented as auxiliary GETs against an existing job's
report so they remain idempotent.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from medfuel.db.registry import DocumentRegistry
from medfuel.db.session import get_sessionmaker
from medfuel.ip.db_orm import (
    IPCitationRow,
    IPFindingRow,
    IPPatentFamilyRow,
    IPReportRunRow,
)
from medfuel.ip.ingest.pipeline import run_ip_discovery
from medfuel.ip.models import IPReportPlan
from medfuel.ip.render import IPReportBuilder
from medfuel.models.schemas import CompanyIdentity, JurisdictionScope, SourceType

router = APIRouter(prefix="/v1/ip", tags=["ip"])


def _session() -> Session:
    return get_sessionmaker()()


def get_db() -> Session:
    session = _session()
    try:
        yield session
    finally:
        session.close()


# --------------------------------------------------------------------------- jobs
class IPReportPlanIn(BaseModel):
    requested_pages: int = Field(default=5, ge=1, le=8)
    soft_max_pages: int = 7
    hard_max_pages: int = 8


class IPJobCreateRequest(BaseModel):
    company: CompanyIdentity
    scope: JurisdictionScope = Field(
        default_factory=lambda: JurisdictionScope(
            sources=[
                SourceType.USPTO,
                SourceType.PATENTSVIEW,
                SourceType.GOOGLE_PATENTS,
                SourceType.EPO,
                SourceType.USPTO_ASSIGNMENT,
                SourceType.PTAB,
                SourceType.LITIGATION,
            ]
        )
    )
    report_plan: IPReportPlanIn = Field(default_factory=IPReportPlanIn)


class IPJobCreateResponse(BaseModel):
    job_id: str
    company_id: str
    status: str = "queued"


class IPJobStatusResponse(BaseModel):
    job_id: str
    company_id: str
    status: str
    result_summary: dict[str, Any] | None = None
    error: str | None = None


async def _execute_ip_job(
    *,
    identity: CompanyIdentity,
    scope: JurisdictionScope,
    requested_pages: int,
    soft_max_pages: int,
    hard_max_pages: int,
    job_id: str,
) -> None:
    session = _session()
    try:
        await run_ip_discovery(
            identity=identity,
            scope=scope,
            job_id=job_id,
            requested_pages=requested_pages,
            soft_max_pages=soft_max_pages,
            hard_max_pages=hard_max_pages,
            session=session,
        )
    finally:
        session.close()


@router.post("/jobs", response_model=IPJobCreateResponse, status_code=202)
def create_ip_job(
    payload: IPJobCreateRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> IPJobCreateResponse:
    registry = DocumentRegistry(db)
    company = registry.upsert_company(payload.company)
    job = registry.create_job(
        company_id=company.company_id,
        request_payload={
            "identity": payload.company.model_dump(),
            "scope": payload.scope.model_dump(),
            "report_plan": payload.report_plan.model_dump(),
            "module": "ip",
        },
        requested_pages=payload.report_plan.requested_pages,
    )
    db.commit()
    background.add_task(
        _execute_ip_job,
        identity=payload.company,
        scope=payload.scope,
        requested_pages=payload.report_plan.requested_pages,
        soft_max_pages=payload.report_plan.soft_max_pages,
        hard_max_pages=payload.report_plan.hard_max_pages,
        job_id=job.job_id,
    )
    return IPJobCreateResponse(job_id=job.job_id, company_id=company.company_id)


@router.get("/jobs/{job_id}", response_model=IPJobStatusResponse)
def get_ip_job(job_id: str, db: Session = Depends(get_db)) -> IPJobStatusResponse:
    registry = DocumentRegistry(db)
    job = registry.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return IPJobStatusResponse(
        job_id=job.job_id,
        company_id=job.company_id,
        status=job.status,
        result_summary=job.result_summary,
        error=job.error,
    )


# --------------------------------------------------------------------------- reports
class IPReportResponse(BaseModel):
    report_id: str
    company_id: str
    status: str
    pages_requested: int
    pages_rendered: int
    adaptive_expansion_triggered: bool
    layout_plan: dict[str, Any]
    confidence_summary: dict[str, int]
    portfolio_summary: dict[str, Any]
    narrative_model: str | None
    extraction_model: str | None


class IPCitationOut(BaseModel):
    inline_number: int
    finding_id: str | None
    source_doc_id: str
    url: str
    locator: str | None = None
    source_confidence: str
    evidence_kind: str


class IPCitationListResponse(BaseModel):
    report_id: str
    citations: list[IPCitationOut]


class IPRerenderRequest(BaseModel):
    requested_pages: int = Field(default=5, ge=1, le=8)
    soft_max_pages: int = 7
    hard_max_pages: int = 8


@router.get("/reports/{report_id}", response_model=IPReportResponse)
def get_ip_report(report_id: str, db: Session = Depends(get_db)) -> IPReportResponse:
    row = db.get(IPReportRunRow, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"IP report not found: {report_id}")
    return IPReportResponse(
        report_id=row.report_id,
        company_id=row.company_id,
        status=row.status,
        pages_requested=row.pages_requested,
        pages_rendered=row.pages_rendered,
        adaptive_expansion_triggered=row.adaptive_expansion_triggered,
        layout_plan=row.layout_plan or {},
        confidence_summary=row.confidence_summary or {},
        portfolio_summary=row.portfolio_summary or {},
        narrative_model=row.narrative_model,
        extraction_model=row.extraction_model,
    )


@router.get("/reports/{report_id}/narrative", response_class=PlainTextResponse)
def get_ip_report_narrative(report_id: str, db: Session = Depends(get_db)) -> str:
    row = db.get(IPReportRunRow, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"IP report not found: {report_id}")
    return row.narrative_text or ""


@router.get("/reports/{report_id}/citations", response_model=IPCitationListResponse)
def get_ip_report_citations(
    report_id: str, db: Session = Depends(get_db)
) -> IPCitationListResponse:
    row = db.get(IPReportRunRow, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"IP report not found: {report_id}")
    rows = (
        db.query(IPCitationRow)
        .filter(IPCitationRow.report_id == report_id)
        .order_by(IPCitationRow.inline_number)
        .all()
    )
    return IPCitationListResponse(
        report_id=report_id,
        citations=[
            IPCitationOut(
                inline_number=r.inline_number,
                finding_id=r.finding_id,
                source_doc_id=r.source_doc_id,
                url=r.url,
                locator=r.locator,
                source_confidence=r.source_confidence,
                evidence_kind=r.evidence_kind,
            )
            for r in rows
        ],
    )


@router.post("/reports/{report_id}/rerender", response_model=IPReportResponse)
async def rerender_ip_report(
    report_id: str,
    payload: IPRerenderRequest,
    db: Session = Depends(get_db),
) -> IPReportResponse:
    existing = db.get(IPReportRunRow, report_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"IP report not found: {report_id}")
    builder = IPReportBuilder(db)
    new_row = await builder.build(
        company_id=existing.company_id,
        job_id=existing.job_id,
        plan=IPReportPlan(
            company_id=existing.company_id,
            requested_pages=payload.requested_pages,
            soft_max_pages=payload.soft_max_pages,
            hard_max_pages=payload.hard_max_pages,
        ),
    )
    db.commit()
    return IPReportResponse(
        report_id=new_row.report_id,
        company_id=new_row.company_id,
        status=new_row.status,
        pages_requested=new_row.pages_requested,
        pages_rendered=new_row.pages_rendered,
        adaptive_expansion_triggered=new_row.adaptive_expansion_triggered,
        layout_plan=new_row.layout_plan or {},
        confidence_summary=new_row.confidence_summary or {},
        portfolio_summary=new_row.portfolio_summary or {},
        narrative_model=new_row.narrative_model,
        extraction_model=new_row.extraction_model,
    )


# --------------------------------------------------------------------------- introspection
class IPFamilyOut(BaseModel):
    family_id: str
    representative_title: str
    members: int
    jurisdictions: int
    signal_score: float
    framework_scores: dict[str, Any]


class IPFindingOut(BaseModel):
    finding_id: str
    family_id: str | None
    category: str
    text: str
    verification_state: str
    confidence: str
    signal_score: float
    citation_numbers: list[int]


@router.get("/companies/{company_id}/families", response_model=list[IPFamilyOut])
def list_ip_families(company_id: str, db: Session = Depends(get_db)) -> list[IPFamilyOut]:
    rows = (
        db.query(IPPatentFamilyRow)
        .filter(IPPatentFamilyRow.company_id == company_id)
        .order_by(IPPatentFamilyRow.signal_score.desc())
        .all()
    )
    return [
        IPFamilyOut(
            family_id=r.family_id,
            representative_title=r.representative_title,
            members=len(r.member_patent_ids or []),
            jurisdictions=len(r.coverage_payload or []),
            signal_score=r.signal_score,
            framework_scores=r.framework_scores or {},
        )
        for r in rows
    ]


@router.get("/reports/{report_id}/findings", response_model=list[IPFindingOut])
def list_ip_findings(report_id: str, db: Session = Depends(get_db)) -> list[IPFindingOut]:
    report = db.get(IPReportRunRow, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"IP report not found: {report_id}")
    rows = (
        db.query(IPFindingRow)
        .filter(IPFindingRow.company_id == report.company_id)
        .order_by(IPFindingRow.signal_score.desc())
        .all()
    )
    return [
        IPFindingOut(
            finding_id=r.finding_id,
            family_id=r.family_id,
            category=r.category,
            text=r.text,
            verification_state=r.verification_state,
            confidence=r.confidence,
            signal_score=r.signal_score,
            citation_numbers=list(r.citation_numbers or []),
        )
        for r in rows
    ]
