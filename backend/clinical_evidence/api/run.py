"""POST /clinical-evidence/run — kick off the full pipeline."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from clinical_evidence.api import runner
from clinical_evidence.schemas import CompanyContext, RunState, SectionPayload

router = APIRouter()


@router.post("/run", response_model=RunState)
async def start_run(company: CompanyContext) -> RunState:
    return runner.launch(company)


@router.get("/{run_id}", response_model=RunState)
async def get_state(run_id: str) -> RunState:
    state = runner.state_of(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run not found")
    return state


@router.get("/{run_id}/payload", response_model=SectionPayload)
async def get_payload(run_id: str) -> SectionPayload:
    payload = runner.payload_of(run_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="payload not ready")
    return payload
