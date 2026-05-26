from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from medfuel.config import get_settings
from medfuel.db.orm import CitationRow, ReportRunRow
from medfuel.db.registry import DocumentRegistry
from medfuel.db.session import get_sessionmaker
from medfuel.ingest.pipeline import run_discovery
from medfuel.models.extraction import ReportPlan
from medfuel.models.schemas import CompanyIdentity, JurisdictionScope, SourceType
from medfuel.render import ReportBuilder

router = APIRouter(prefix="/v1/regulatory", tags=["regulatory"])


def _session() -> Session:
    return get_sessionmaker()()


def get_db() -> Session:
    session = _session()
    try:
        yield session
    finally:
        session.close()


class ReportPlanIn(BaseModel):
    # Aim is 6 pages; the layout engine may expand up to max_pages only when
    # critical items would otherwise be omitted.
    requested_pages: int = Field(default=6, ge=1, le=10)
    max_pages: int = 10
    english_only: bool = True


class JobCreateRequest(BaseModel):
    company: CompanyIdentity
    scope: JurisdictionScope = Field(default_factory=JurisdictionScope)
    report_plan: ReportPlanIn = Field(default_factory=ReportPlanIn)


class JobCreateResponse(BaseModel):
    job_id: str
    company_id: str
    status: str = "queued"


class JobStatusResponse(BaseModel):
    job_id: str
    company_id: str
    status: str
    result_summary: dict[str, Any] | None = None
    error: str | None = None


async def _execute_job(
    *,
    identity: CompanyIdentity,
    scope: JurisdictionScope,
    requested_pages: int,
    max_pages: int,
    job_id: str,
) -> None:
    session = _session()
    try:
        await run_discovery(
            identity=identity,
            scope=scope,
            job_id=job_id,
            requested_pages=requested_pages,
            max_pages=max_pages,
            session=session,
        )
    finally:
        session.close()


@router.post("/jobs", response_model=JobCreateResponse, status_code=202)
def create_job(
    payload: JobCreateRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    registry = DocumentRegistry(db)
    company = registry.upsert_company(payload.company)
    job = registry.create_job(
        company_id=company.company_id,
        request_payload={
            "identity": payload.company.model_dump(),
            "scope": payload.scope.model_dump(),
            "report_plan": payload.report_plan.model_dump(),
        },
        requested_pages=payload.report_plan.requested_pages,
    )
    db.commit()
    background.add_task(
        _execute_job,
        identity=payload.company,
        scope=payload.scope,
        requested_pages=payload.report_plan.requested_pages,
        max_pages=payload.report_plan.max_pages,
        job_id=job.job_id,
    )
    return JobCreateResponse(job_id=job.job_id, company_id=company.company_id)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    registry = DocumentRegistry(db)
    job = registry.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return JobStatusResponse(
        job_id=job.job_id,
        company_id=job.company_id,
        status=job.status,
        result_summary=job.result_summary,
        error=job.error,
    )


# --------------------------------------------------------------------- reports
class ReportResponse(BaseModel):
    report_id: str
    company_id: str
    status: str
    pages_requested: int
    pages_rendered: int
    adaptive_expansion_triggered: bool
    layout_plan: dict[str, Any]
    confidence_summary: dict[str, int]
    narrative_model: str | None
    extraction_model: str | None


class CitationOut(BaseModel):
    inline_number: int
    claim_id: str | None
    source_doc_id: str
    url: str
    locator: str | None = None
    source_confidence: str


class CitationListResponse(BaseModel):
    report_id: str
    citations: list[CitationOut]


class RerenderRequest(BaseModel):
    requested_pages: int = Field(default=6, ge=1, le=10)
    max_pages: int = 10


@router.get("/reports/{report_id}", response_model=ReportResponse)
def get_report(report_id: str, db: Session = Depends(get_db)) -> ReportResponse:
    row = db.get(ReportRunRow, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")
    return ReportResponse(
        report_id=row.report_id,
        company_id=row.company_id,
        status=row.status,
        pages_requested=row.pages_requested,
        pages_rendered=row.pages_rendered,
        adaptive_expansion_triggered=row.adaptive_expansion_triggered,
        layout_plan=row.layout_plan or {},
        confidence_summary=row.confidence_summary or {},
        narrative_model=row.narrative_model,
        extraction_model=row.extraction_model,
    )


@router.get("/reports/{report_id}/narrative", response_class=PlainTextResponse)
def get_report_narrative(report_id: str, db: Session = Depends(get_db)) -> str:
    row = db.get(ReportRunRow, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")
    return row.narrative_text or ""


@router.get("/reports/{report_id}/citations", response_model=CitationListResponse)
def get_report_citations(report_id: str, db: Session = Depends(get_db)) -> CitationListResponse:
    row = db.get(ReportRunRow, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")
    rows = (
        db.query(CitationRow)
        .filter(CitationRow.report_id == report_id)
        .order_by(CitationRow.inline_number)
        .all()
    )
    return CitationListResponse(
        report_id=report_id,
        citations=[
            CitationOut(
                inline_number=r.inline_number,
                claim_id=r.claim_id,
                source_doc_id=r.source_doc_id,
                url=r.url,
                locator=r.locator,
                source_confidence=r.source_confidence,
            )
            for r in rows
        ],
    )


# --------------------------------------------------------------------- sources
class SourceHealthEntry(BaseModel):
    source_type: SourceType
    configured: bool
    requires_api_key: bool
    api_key_present: bool
    rate_limit_hint: str | None = None


class SourceHealthResponse(BaseModel):
    sources: list[SourceHealthEntry]


@router.get("/sources/health", response_model=SourceHealthResponse)
def sources_health() -> SourceHealthResponse:
    """Static configuration health for each adapter.

    Reports which adapters will function with the current environment. We
    deliberately do NOT issue outbound calls here so the endpoint stays cheap
    and never advertises a "live" status that's only true at the moment of
    polling. For real connectivity checks use the discovery pipeline.
    """
    settings = get_settings()
    rows: list[SourceHealthEntry] = [
        SourceHealthEntry(
            source_type=SourceType.FDA,
            configured=True,
            requires_api_key=False,
            api_key_present=bool(settings.openfda_api_key),
            rate_limit_hint=f"{settings.openfda_rate_per_minute}/min",
        ),
        SourceHealthEntry(
            source_type=SourceType.SEC,
            configured=True,
            requires_api_key=False,
            api_key_present=True,
            rate_limit_hint=f"{settings.sec_rate_per_second}/sec",
        ),
        SourceHealthEntry(
            source_type=SourceType.CLINICALTRIALS,
            configured=True,
            requires_api_key=False,
            api_key_present=True,
            rate_limit_hint=f"{settings.clinicaltrials_rate_per_second}/sec",
        ),
        SourceHealthEntry(
            source_type=SourceType.PUBMED,
            configured=True,
            requires_api_key=False,
            api_key_present=bool(settings.ncbi_api_key),
            rate_limit_hint=f"{settings.ncbi_rate_per_second}/sec (10/sec with key)",
        ),
        SourceHealthEntry(
            source_type=SourceType.EMA,
            configured=True,
            requires_api_key=False,
            api_key_present=True,
            rate_limit_hint=f"{settings.ema_rate_per_second}/sec",
        ),
        SourceHealthEntry(
            source_type=SourceType.USPTO,
            configured=True,
            requires_api_key=False,
            api_key_present=bool(settings.uspto_api_key),
            rate_limit_hint=f"{settings.uspto_rate_per_second}/sec",
        ),
        SourceHealthEntry(
            source_type=SourceType.MHRA,
            configured=bool(settings.firecrawl_api_key),
            requires_api_key=True,
            api_key_present=bool(settings.firecrawl_api_key),
            rate_limit_hint=f"{settings.firecrawl_rate_per_second}/sec (via Firecrawl)",
        ),
        SourceHealthEntry(
            source_type=SourceType.PMDA,
            configured=bool(settings.firecrawl_api_key),
            requires_api_key=True,
            api_key_present=bool(settings.firecrawl_api_key),
            rate_limit_hint=f"{settings.firecrawl_rate_per_second}/sec (via Firecrawl)",
        ),
        SourceHealthEntry(
            source_type=SourceType.COMPANY,
            configured=bool(settings.firecrawl_api_key),
            requires_api_key=True,
            api_key_present=bool(settings.firecrawl_api_key),
            rate_limit_hint=f"{settings.firecrawl_rate_per_second}/sec (via Firecrawl)",
        ),
    ]
    return SourceHealthResponse(sources=rows)


@router.post("/reports/{report_id}/rerender", response_model=ReportResponse)
async def rerender_report(
    report_id: str,
    payload: RerenderRequest,
    db: Session = Depends(get_db),
) -> ReportResponse:
    existing = db.get(ReportRunRow, report_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")
    builder = ReportBuilder(db)
    new_row = await builder.build(
        company_id=existing.company_id,
        job_id=existing.job_id,
        plan=ReportPlan(
            company_id=existing.company_id,
            requested_pages=payload.requested_pages,
            max_pages=payload.max_pages,
        ),
    )
    db.commit()
    return ReportResponse(
        report_id=new_row.report_id,
        company_id=new_row.company_id,
        status=new_row.status,
        pages_requested=new_row.pages_requested,
        pages_rendered=new_row.pages_rendered,
        adaptive_expansion_triggered=new_row.adaptive_expansion_triggered,
        layout_plan=new_row.layout_plan or {},
        confidence_summary=new_row.confidence_summary or {},
        narrative_model=new_row.narrative_model,
        extraction_model=new_row.extraction_model,
    )
