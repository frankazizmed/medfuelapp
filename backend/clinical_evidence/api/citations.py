"""GET /clinical-evidence/{run_id}/citations — fetch the citation list."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from clinical_evidence.api import runner
from clinical_evidence.schemas import Citation

router = APIRouter()


@router.get("/{run_id}/citations", response_model=list[Citation])
async def get_citations(run_id: str) -> list[Citation]:
    payload = runner.payload_of(run_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="payload not ready")
    return payload.citations
