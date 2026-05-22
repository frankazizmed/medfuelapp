from __future__ import annotations

from datetime import UTC, datetime

import pytest

from medfuel.adapters.base import SourceAdapter
from medfuel.db.registry import hash_payload
from medfuel.ingest.pipeline import DiscoveryPipeline, run_discovery
from medfuel.models.schemas import (
    OFFICIAL_RANK,
    CompanyIdentity,
    JurisdictionScope,
    RawSourceRecord,
    SourceType,
)


class _StubAdapter(SourceAdapter):
    def __init__(self, source_type: SourceType, jurisdiction: str, records: list[RawSourceRecord]):
        self.source_type = source_type
        self.jurisdiction = jurisdiction
        self._records = records

    async def discover(self, identity, scope):
        return list(self._records)


class _FailingAdapter(SourceAdapter):
    source_type = SourceType.SEC
    jurisdiction = "US"

    async def discover(self, identity, scope):
        raise RuntimeError("boom")


def _make_record(source: SourceType, juris: str, url: str, payload: dict) -> RawSourceRecord:
    return RawSourceRecord(
        source_type=source,
        jurisdiction=juris,
        url=url,
        title="t",
        payload=payload,
        retrieved_at=datetime.now(UTC),
        content_hash=hash_payload(url, payload, title="t"),
        official_rank=OFFICIAL_RANK[source],
    )


@pytest.mark.asyncio
async def test_pipeline_aggregates_and_isolates_failures(db_session):
    fda_records = [
        _make_record(SourceType.FDA, "US", "https://api.fda.gov/x/1", {"a": 1}),
        _make_record(SourceType.FDA, "US", "https://api.fda.gov/x/2", {"a": 2}),
    ]
    ct_records = [
        _make_record(SourceType.CLINICALTRIALS, "GLOBAL", "https://ct.gov/x/1", {"b": 1}),
    ]
    pipeline = DiscoveryPipeline(
        adapters=[
            _StubAdapter(SourceType.FDA, "US", fda_records),
            _StubAdapter(SourceType.CLINICALTRIALS, "GLOBAL", ct_records),
            _FailingAdapter(),
        ]
    )

    result = await run_discovery(
        identity=CompanyIdentity(name="Example Tx"),
        scope=JurisdictionScope(
            sources=[SourceType.FDA, SourceType.CLINICALTRIALS, SourceType.SEC]
        ),
        pipeline=pipeline,
        session=db_session,
    )

    assert result.records_collected == 3
    assert result.records_persisted_new == 3
    assert result.records_persisted_duplicate == 0
    assert result.by_source[SourceType.FDA] == 2
    assert result.by_source[SourceType.CLINICALTRIALS] == 1
    assert any("boom" in e for e in result.errors)

    # Re-running the same pipeline should dedupe everything as it is now persisted.
    result2 = await run_discovery(
        identity=CompanyIdentity(name="Example Tx"),
        scope=JurisdictionScope(
            sources=[SourceType.FDA, SourceType.CLINICALTRIALS, SourceType.SEC]
        ),
        pipeline=pipeline,
        session=db_session,
    )
    assert result2.records_persisted_new == 0
    assert result2.records_persisted_duplicate == 3
