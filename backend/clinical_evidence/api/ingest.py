"""POST /clinical-evidence/ingest — discovery + ingestion only."""

from __future__ import annotations

from fastapi import APIRouter

from clinical_evidence.discovery.orchestrator import discover
from clinical_evidence.schemas import CompanyContext, DiscoveryResult

router = APIRouter()


@router.post("/ingest", response_model=DiscoveryResult)
async def ingest(company: CompanyContext) -> DiscoveryResult:
    return await discover(company)
