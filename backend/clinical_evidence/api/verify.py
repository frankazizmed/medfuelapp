"""POST /clinical-evidence/verify — reconcile findings across sources."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from clinical_evidence.schemas import ClinicalFinding, DiscoveryResult
from clinical_evidence.verification.crosscheck import reconcile


class VerifyRequest(BaseModel):
    findings: list[ClinicalFinding]
    discovery: DiscoveryResult


router = APIRouter()


@router.post("/verify", response_model=list[ClinicalFinding])
async def verify(req: VerifyRequest) -> list[ClinicalFinding]:
    return reconcile(
        req.findings,
        documents=req.discovery.documents,
        trials=req.discovery.trials,
        publications=req.discovery.publications,
    )
