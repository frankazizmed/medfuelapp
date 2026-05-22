"""POST /clinical-evidence/extract — extract findings from a discovery result."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from clinical_evidence.extraction.runner import run_extraction
from clinical_evidence.schemas import ClinicalFinding, DiscoveryResult


class ExtractRequest(BaseModel):
    company_id: str
    discovery: DiscoveryResult


router = APIRouter()


@router.post("/extract", response_model=list[ClinicalFinding])
async def extract(req: ExtractRequest) -> list[ClinicalFinding]:
    return await run_extraction(
        company_id=req.company_id,
        documents=req.discovery.documents,
        trials=req.discovery.trials,
        publications=req.discovery.publications,
    )
