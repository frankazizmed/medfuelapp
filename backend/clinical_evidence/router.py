"""The single APIRouter the host mounts."""

from __future__ import annotations

from fastapi import APIRouter

from clinical_evidence.api import (
    citations,
    extract,
    generate,
    ingest,
    layout,
    pdf,
    run,
    signal_rank,
    verify,
)

router = APIRouter(prefix="/clinical-evidence", tags=["clinical-evidence"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"island": "clinical-evidence", "status": "ok"}


# Static-prefix routes first so they aren't shadowed by /{run_id}.
router.include_router(ingest.router)
router.include_router(extract.router)
router.include_router(verify.router)
router.include_router(signal_rank.router)
router.include_router(generate.router)
router.include_router(layout.router)
router.include_router(citations.router)
router.include_router(pdf.router)
# Dynamic /{run_id} routes last.
router.include_router(run.router)
