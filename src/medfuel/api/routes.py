from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from medfuel.db.registry import DocumentRegistry
from medfuel.db.session import get_sessionmaker
from medfuel.ingest.pipeline import run_discovery
from medfuel.models.schemas import CompanyIdentity, JurisdictionScope

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
    job_id: str,
) -> None:
    session = _session()
    try:
        await run_discovery(
            identity=identity,
            scope=scope,
            job_id=job_id,
            requested_pages=requested_pages,
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
