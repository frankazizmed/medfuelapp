"""In-process async pipeline runner.

This is the one place where every layer is wired together. It's an
intentionally simple async background-task runner so the island ships with
zero infrastructure dependencies. A host app can swap in Celery/RQ/Cloud
Tasks by replacing only ``launch`` and ``state_of``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from clinical_evidence.citations.builder import build as build_citations
from clinical_evidence.discovery.orchestrator import discover
from clinical_evidence.extraction.runner import run_extraction
from clinical_evidence.layout.composer import compose
from clinical_evidence.layout.page_budget import decide as decide_pages
from clinical_evidence.narrative.generator import _findings_for_page, generate_pages
from clinical_evidence.schemas import (
    CompanyContext,
    RunState,
    RunStatus,
    SectionPayload,
)
from clinical_evidence.signal.filter import filter_noise
from clinical_evidence.signal.scorer import score_findings
from clinical_evidence.verification.crosscheck import reconcile

log = logging.getLogger(__name__)


_RUNS: dict[str, RunState] = {}
_PAYLOADS: dict[str, SectionPayload] = {}
_TASKS: dict[str, asyncio.Task] = {}


def _set(run_id: str, *, status: RunStatus, error: str | None = None) -> None:
    state = _RUNS[run_id]
    state.status = status
    state.updated_at = datetime.now(timezone.utc)
    if error is not None:
        state.error = error


async def _run(run_id: str, company: CompanyContext) -> None:
    try:
        _set(run_id, status=RunStatus.discovering)
        discovery = await discover(company)

        _set(run_id, status=RunStatus.ingesting)
        # Ingestion is handled inline by extraction via normalize().

        _set(run_id, status=RunStatus.extracting)
        findings = await run_extraction(
            company_id=company.company_id,
            documents=discovery.documents,
            trials=discovery.trials,
            publications=discovery.publications,
        )

        _set(run_id, status=RunStatus.verifying)
        findings = reconcile(
            findings,
            documents=discovery.documents,
            trials=discovery.trials,
            publications=discovery.publications,
        )

        _set(run_id, status=RunStatus.scoring)
        findings = score_findings(findings, trials=discovery.trials)
        findings = filter_noise(findings)

        citations = build_citations(findings=findings, documents=discovery.documents)

        page_count, omitted_fraction = decide_pages(
            findings,
            per_page_findings=_findings_for_page,
        )

        _set(run_id, status=RunStatus.generating)
        pages = generate_pages(
            findings=findings,
            trials=discovery.trials,
            citations=citations,
            company_name=company.name,
            page_count=page_count,
        )

        _set(run_id, status=RunStatus.laying_out)
        payload = compose(
            run_id=run_id,
            company_id=company.company_id,
            company_name=company.name,
            pages=pages,
            citations=citations,
            omitted_fraction=omitted_fraction,
            page_count=page_count,
        )
        _PAYLOADS[run_id] = payload
        _set(run_id, status=RunStatus.ready)
        log.info("Run %s ready (%d pages, %d citations)", run_id, page_count, len(citations))
    except Exception as exc:  # noqa: BLE001
        log.exception("Run %s failed: %s", run_id, exc)
        _set(run_id, status=RunStatus.failed, error=str(exc))


def launch(company: CompanyContext) -> RunState:
    run_id = f"run-{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    state = RunState(
        run_id=run_id,
        company_id=company.company_id,
        status=RunStatus.queued,
        started_at=now,
        updated_at=now,
    )
    _RUNS[run_id] = state
    _TASKS[run_id] = asyncio.create_task(_run(run_id, company))
    return state


def state_of(run_id: str) -> RunState | None:
    return _RUNS.get(run_id)


def payload_of(run_id: str) -> SectionPayload | None:
    return _PAYLOADS.get(run_id)
