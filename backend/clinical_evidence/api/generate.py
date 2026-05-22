"""POST /clinical-evidence/generate — produce page-structured narrative JSON."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from clinical_evidence.narrative.generator import generate_pages
from clinical_evidence.schemas import Citation, ClinicalFinding, Page, Trial


class GenerateRequest(BaseModel):
    findings: list[ClinicalFinding]
    trials: list[Trial]
    citations: list[Citation]
    company_name: str
    page_count: int = 6
    use_llm: bool = True


router = APIRouter()


@router.post("/generate", response_model=list[Page])
async def generate(req: GenerateRequest) -> list[Page]:
    return generate_pages(
        findings=req.findings,
        trials=req.trials,
        citations=req.citations,
        company_name=req.company_name,
        page_count=req.page_count,
        use_llm=req.use_llm,
    )
