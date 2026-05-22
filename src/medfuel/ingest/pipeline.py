from __future__ import annotations

import asyncio
import logging
from collections import Counter

from sqlalchemy.orm import Session

from medfuel.adapters import (
    ClinicalTrialsAdapter,
    CompanyWebAdapter,
    EMAAdapter,
    FDAAdapter,
    FirecrawlClient,
    MHRAAdapter,
    NCBIAdapter,
    PMDAAdapter,
    SECAdapter,
    SourceAdapter,
    USPTOAdapter,
)
from medfuel.db.registry import DocumentRegistry
from medfuel.db.session import get_sessionmaker
from medfuel.extract import ExtractionOrchestrator
from medfuel.models.extraction import ReportPlan
from medfuel.models.schemas import (
    CompanyIdentity,
    DiscoveryResult,
    JurisdictionScope,
    RawSourceRecord,
    SourceType,
)
from medfuel.observability import bind_job_context, clear_job_context, span
from medfuel.render import ReportBuilder
from medfuel.verify import Verifier

log = logging.getLogger(__name__)


class DiscoveryPipeline:
    """Fans out discovery across all configured adapters in parallel.

    Each adapter failure is captured as an error string but does not abort the
    other adapters: the goal in Phase 1 is repeatable collection with provenance,
    not a fail-fast contract.
    """

    def __init__(self, adapters: list[SourceAdapter] | None = None):
        self._adapters = adapters or self._default_adapters()

    @staticmethod
    def _default_adapters() -> list[SourceAdapter]:
        firecrawl = FirecrawlClient()
        return [
            FDAAdapter(),
            SECAdapter(),
            ClinicalTrialsAdapter(),
            NCBIAdapter(),
            EMAAdapter(),
            USPTOAdapter(),
            MHRAAdapter(firecrawl=firecrawl),
            PMDAAdapter(firecrawl=firecrawl),
            CompanyWebAdapter(firecrawl=firecrawl),
        ]

    async def aclose(self) -> None:
        for adapter in self._adapters:
            close = getattr(adapter, "aclose", None)
            if close is None:
                continue
            try:
                await close()
            except Exception:  # noqa: BLE001
                log.warning("adapter close failed: %s", adapter.name, exc_info=True)

    async def collect(
        self,
        identity: CompanyIdentity,
        scope: JurisdictionScope,
    ) -> tuple[list[RawSourceRecord], list[str], dict[SourceType, int]]:
        scoped = [a for a in self._adapters if a.source_type in scope.sources]
        results = await asyncio.gather(
            *(a.discover(identity, scope) for a in scoped),
            return_exceptions=True,
        )
        records: list[RawSourceRecord] = []
        errors: list[str] = []
        by_source: Counter[SourceType] = Counter()
        for adapter, result in zip(scoped, results, strict=True):
            if isinstance(result, Exception):
                errors.append(f"{adapter.name}: {result!r}")
                log.warning("adapter %s failed", adapter.name, exc_info=result)
                continue
            records.extend(result)
            by_source[adapter.source_type] += len(result)
        return records, errors, dict(by_source)


async def run_discovery(
    *,
    identity: CompanyIdentity,
    scope: JurisdictionScope,
    job_id: str | None = None,
    requested_pages: int = 6,
    max_pages: int = 10,
    pipeline: DiscoveryPipeline | None = None,
    session: Session | None = None,
    build_report: bool = True,
) -> DiscoveryResult:
    """Orchestrate a single discovery run end-to-end.

    The caller may inject a session for tests; otherwise we open one from the
    application sessionmaker. The pipeline is closed only if it was created here
    so test harnesses can reuse a pre-wired pipeline across calls.
    """

    own_pipeline = False
    if pipeline is None:
        pipeline = DiscoveryPipeline()
        own_pipeline = True
    own_session = False
    if session is None:
        session = get_sessionmaker()()
        own_session = True

    try:
        registry = DocumentRegistry(session)
        company = registry.upsert_company(identity)
        if job_id is None:
            job = registry.create_job(
                company_id=company.company_id,
                request_payload={
                    "identity": identity.model_dump(),
                    "scope": scope.model_dump(),
                },
                requested_pages=requested_pages,
            )
            job_id = job.job_id
        bind_job_context(job_id=job_id, company_id=company.company_id, company=identity.name)
        registry.update_job(job_id, status="running")
        session.commit()

        with span("discovery.collect"):
            records, errors, by_source = await pipeline.collect(identity, scope)

        with span("discovery.persist", count=len(records)):
            new_count, dup_count = registry.persist_records(
                company.company_id, job_id, records
            )
            session.commit()

        events_persisted = 0
        claims_persisted = 0
        report_id: str | None = None

        if build_report:
            extractor_orch = ExtractionOrchestrator()
            with span("extract.run"):
                candidate_pairs = await extractor_orch.run(
                    session=session, company_id=company.company_id, job_id=job_id
                )
                session.commit()

            with span("verify.run", candidates=len(candidate_pairs)):
                verifier = Verifier(session)
                verification = verifier.run(
                    company_id=company.company_id,
                    job_id=job_id,
                    candidate_pairs=candidate_pairs,
                )
                events_persisted = len(verification.events)
                claims_persisted = len(verification.claims)
                session.commit()

            with span("render.build", events=events_persisted, claims=claims_persisted):
                builder = ReportBuilder(session)
                report_row = await builder.build(
                    company_id=company.company_id,
                    job_id=job_id,
                    plan=ReportPlan(
                        company_id=company.company_id,
                        requested_pages=requested_pages,
                        max_pages=max_pages,
                    ),
                )
                report_id = report_row.report_id
                session.commit()

        result = DiscoveryResult(
            company_id=company.company_id,
            job_id=job_id,
            records_collected=len(records),
            records_persisted_new=new_count,
            records_persisted_duplicate=dup_count,
            by_source=by_source,
            errors=errors,
            events_persisted=events_persisted,
            claims_persisted=claims_persisted,
            report_id=report_id,
        )
        registry.update_job(
            job_id,
            status="complete" if not errors else "complete_with_errors",
            result_summary=result.model_dump(mode="json"),
        )
        session.commit()
        return result
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        if job_id is not None:
            try:
                registry = DocumentRegistry(session)
                registry.update_job(job_id, status="failed", error=str(exc))
                session.commit()
            except Exception:  # noqa: BLE001
                session.rollback()
        raise
    finally:
        if own_pipeline:
            await pipeline.aclose()
        if own_session:
            session.close()
        clear_job_context()
