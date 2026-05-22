"""IP discovery pipeline.

Fans out across IP source adapters in parallel, persists raw records
to the shared registry, runs IP extraction (patents → families →
proceedings), and builds an IP report run. The same DocumentRegistry
is used so dedupe + audit trails work identically to the regulatory
pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter

from sqlalchemy.orm import Session

from medfuel.adapters import FirecrawlClient, USPTOAdapter
from medfuel.adapters.base import SourceAdapter
from medfuel.db.registry import DocumentRegistry
from medfuel.db.session import get_sessionmaker
from medfuel.ip.adapters import (
    EPOAdapter,
    GooglePatentsAdapter,
    LitigationAdapter,
    PatentsViewAdapter,
    PTABAdapter,
    USPTOAssignmentAdapter,
)
from medfuel.ip.extract import IPExtractionOrchestrator
from medfuel.ip.models import (
    IPDiscoveryResult,
    IPReportPlan,
    IPSourceType,
)
from medfuel.ip.render import IPReportBuilder
from medfuel.models.schemas import (
    CompanyIdentity,
    JurisdictionScope,
    RawSourceRecord,
    SourceType,
)

log = logging.getLogger(__name__)


# Map from registry SourceType back to IPSourceType for the result summary.
_IP_SOURCE_FROM_REGISTRY: dict[SourceType, IPSourceType] = {
    SourceType.USPTO: IPSourceType.USPTO,
    SourceType.PATENTSVIEW: IPSourceType.PATENTSVIEW,
    SourceType.GOOGLE_PATENTS: IPSourceType.GOOGLE_PATENTS,
    SourceType.EPO: IPSourceType.EPO,
    SourceType.WIPO: IPSourceType.WIPO,
    SourceType.USPTO_ASSIGNMENT: IPSourceType.USPTO_ASSIGNMENT,
    SourceType.PTAB: IPSourceType.PTAB,
    SourceType.LITIGATION: IPSourceType.LITIGATION,
    SourceType.SEC_IP: IPSourceType.SEC_IP,
    SourceType.COMPANY_IP: IPSourceType.COMPANY_IP,
}


class IPDiscoveryPipeline:
    def __init__(self, adapters: list[SourceAdapter] | None = None):
        self._adapters = adapters or self._default_adapters()

    @staticmethod
    def _default_adapters() -> list[SourceAdapter]:
        firecrawl = FirecrawlClient()
        return [
            USPTOAdapter(),
            PatentsViewAdapter(),
            GooglePatentsAdapter(firecrawl=firecrawl),
            EPOAdapter(),
            USPTOAssignmentAdapter(),
            PTABAdapter(),
            LitigationAdapter(),
        ]

    async def aclose(self) -> None:
        for adapter in self._adapters:
            close = getattr(adapter, "aclose", None)
            if close is None:
                continue
            try:
                await close()
            except Exception:  # noqa: BLE001
                log.warning("ip adapter close failed: %s", adapter.name, exc_info=True)

    async def collect(
        self,
        identity: CompanyIdentity,
        scope: JurisdictionScope,
    ) -> tuple[list[RawSourceRecord], list[str], dict[SourceType, int]]:
        scoped = [
            a for a in self._adapters
            if a.source_type in scope.sources or _is_ip_source(a.source_type)
        ]
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
                log.warning("ip adapter %s failed", adapter.name, exc_info=result)
                continue
            records.extend(result)
            by_source[adapter.source_type] += len(result)
        return records, errors, dict(by_source)


def _is_ip_source(s: SourceType) -> bool:
    return s in _IP_SOURCE_FROM_REGISTRY


async def run_ip_discovery(
    *,
    identity: CompanyIdentity,
    scope: JurisdictionScope,
    job_id: str | None = None,
    requested_pages: int = 5,
    soft_max_pages: int = 7,
    hard_max_pages: int = 8,
    pipeline: IPDiscoveryPipeline | None = None,
    session: Session | None = None,
    build_report: bool = True,
) -> IPDiscoveryResult:
    own_pipeline = False
    if pipeline is None:
        pipeline = IPDiscoveryPipeline()
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
                    "module": "ip",
                },
                requested_pages=requested_pages,
            )
            job_id = job.job_id
        registry.update_job(job_id, status="running")
        session.commit()

        records, errors, by_source = await pipeline.collect(identity, scope)
        new_count, dup_count = registry.persist_records(
            company.company_id, job_id, records
        )
        session.commit()

        families_persisted = 0
        findings_persisted = 0
        report_id: str | None = None

        if build_report:
            extractor = IPExtractionOrchestrator()
            extraction = extractor.run(
                session=session, company_id=company.company_id, job_id=job_id
            )
            families_persisted = len(extraction.families)
            session.commit()

            builder = IPReportBuilder(session)
            row = await builder.build(
                company_id=company.company_id,
                job_id=job_id,
                plan=IPReportPlan(
                    company_id=company.company_id,
                    requested_pages=requested_pages,
                    soft_max_pages=soft_max_pages,
                    hard_max_pages=hard_max_pages,
                ),
            )
            report_id = row.report_id
            session.commit()
            from medfuel.ip.db_orm import IPFindingRow  # local to avoid cycle on init

            findings_persisted = (
                session.query(IPFindingRow)
                .filter(IPFindingRow.company_id == company.company_id)
                .count()
            )

        ip_by_source = {
            _IP_SOURCE_FROM_REGISTRY[s]: n
            for s, n in by_source.items()
            if s in _IP_SOURCE_FROM_REGISTRY
        }
        result = IPDiscoveryResult(
            company_id=company.company_id,
            job_id=job_id,
            records_collected=len(records),
            records_persisted_new=new_count,
            records_persisted_duplicate=dup_count,
            by_source=ip_by_source,
            errors=errors,
            families_persisted=families_persisted,
            findings_persisted=findings_persisted,
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
