"""POST /clinical-evidence/signal-rank — score + filter findings."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from clinical_evidence.schemas import ClinicalFinding, Trial
from clinical_evidence.signal.filter import filter_noise
from clinical_evidence.signal.scorer import score_findings


class SignalRequest(BaseModel):
    findings: list[ClinicalFinding]
    trials: list[Trial]
    filter_noise: bool = True


router = APIRouter()


@router.post("/signal-rank", response_model=list[ClinicalFinding])
async def signal_rank(req: SignalRequest) -> list[ClinicalFinding]:
    scored = score_findings(req.findings, trials=req.trials)
    if req.filter_noise:
        scored = filter_noise(scored)
    return scored
