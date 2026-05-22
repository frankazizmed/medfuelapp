"""POST /clinical-evidence/layout — adaptive page budget + final composition."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from clinical_evidence.layout.composer import compose
from clinical_evidence.layout.page_budget import decide
from clinical_evidence.narrative.generator import _findings_for_page, generate_pages
from clinical_evidence.schemas import (
    Citation,
    ClinicalFinding,
    SectionPayload,
    Trial,
)


class LayoutRequest(BaseModel):
    run_id: str
    company_id: str
    company_name: str
    findings: list[ClinicalFinding]
    trials: list[Trial]
    citations: list[Citation]


router = APIRouter()


@router.post("/layout", response_model=SectionPayload)
async def lay_out(req: LayoutRequest) -> SectionPayload:
    page_count, omitted = decide(req.findings, per_page_findings=_findings_for_page)
    pages = generate_pages(
        findings=req.findings,
        trials=req.trials,
        citations=req.citations,
        company_name=req.company_name,
        page_count=page_count,
    )
    return compose(
        run_id=req.run_id,
        company_id=req.company_id,
        company_name=req.company_name,
        pages=pages,
        citations=req.citations,
        omitted_fraction=omitted,
        page_count=page_count,
    )
