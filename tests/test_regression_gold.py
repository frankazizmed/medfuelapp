from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from medfuel.adapters.base import SourceAdapter
from medfuel.db.orm import (
    AssetRow,
    ClaimRow,
    RegulatoryEventRow,
    ReportRunRow,
)
from medfuel.db.registry import hash_payload
from medfuel.ingest.pipeline import DiscoveryPipeline, run_discovery
from medfuel.models import CompanyIdentity, JurisdictionScope, RawSourceRecord, SourceType
from medfuel.models.schemas import OFFICIAL_RANK

FIXTURE_DIR = Path(__file__).parent / "gold_set" / "fixtures"


class _FixtureAdapter(SourceAdapter):
    """Adapter that emits a fixed set of pre-recorded records for one SourceType.

    Each archetype fixture is materialized as one adapter per SourceType
    appearing in its records. The pipeline composes them just like real
    adapters, so the rule extractor exercises its production code path.
    """

    def __init__(self, source_type: SourceType, jurisdiction: str, records: list[RawSourceRecord]):
        self.source_type = source_type
        self.jurisdiction = jurisdiction
        self._records = records

    async def discover(self, identity, scope):
        return list(self._records)


def _load_fixtures() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(FIXTURE_DIR.glob("*.json"))]


def _to_records(fixture: dict) -> list[RawSourceRecord]:
    out: list[RawSourceRecord] = []
    for spec in fixture["records"]:
        source = SourceType(spec["source_type"])
        url = spec["url"]
        payload = spec["payload"]
        title = spec.get("title") or url
        out.append(
            RawSourceRecord(
                source_type=source,
                jurisdiction=spec["jurisdiction"],
                url=url,
                title=title,
                payload=payload,
                retrieved_at=datetime.now(UTC),
                content_hash=hash_payload(url, payload, title=title),
                official_rank=OFFICIAL_RANK[source],
            )
        )
    return out


def _adapters_from_fixture(fixture: dict) -> list[SourceAdapter]:
    records = _to_records(fixture)
    by_source: dict[SourceType, list[RawSourceRecord]] = {}
    for rec in records:
        by_source.setdefault(rec.source_type, []).append(rec)
    return [
        _FixtureAdapter(source, recs[0].jurisdiction, recs)
        for source, recs in by_source.items()
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fixture",
    _load_fixtures(),
    ids=lambda fx: fx["archetype"].split(" ")[0].replace("-", "_"),
)
async def test_gold_archetype_extraction_and_scoring(fixture, db_session):
    adapters = _adapters_from_fixture(fixture)
    identity = CompanyIdentity(**fixture["company"])
    scope = JurisdictionScope(sources=[a.source_type for a in adapters])

    result = await run_discovery(
        identity=identity,
        scope=scope,
        pipeline=DiscoveryPipeline(adapters=adapters),
        session=db_session,
    )

    expected = fixture["expected"]

    events = db_session.query(RegulatoryEventRow).all()
    assert len(events) >= expected["min_events"], (
        f"{fixture['archetype']}: expected >= {expected['min_events']} events, got {len(events)}"
    )

    actual_types = {e.event_type for e in events}
    missing_types = set(expected["required_event_types"]) - actual_types
    assert not missing_types, f"{fixture['archetype']}: missing event types {missing_types}"

    actual_agencies = {e.agency for e in events}
    missing_agencies = set(expected["required_agencies"]) - actual_agencies
    assert not missing_agencies, (
        f"{fixture['archetype']}: missing agencies {missing_agencies}"
    )

    if "must_include_asset_substring" in expected:
        substr = expected["must_include_asset_substring"]
        assets = db_session.query(AssetRow).all()
        assert any(substr.lower() in a.asset_name.lower() for a in assets), (
            f"{fixture['archetype']}: no asset matches {substr!r}"
        )

    claims = db_session.query(ClaimRow).all()
    high_signal = [c for c in claims if c.signal_score >= 75.0]
    assert len(high_signal) >= expected["min_high_signal_claims"], (
        f"{fixture['archetype']}: expected >= {expected['min_high_signal_claims']} "
        f"high-signal claims, got {len(high_signal)}"
    )

    # Report must build, render the six-section baseline, and produce
    # a confidence summary covering every persisted claim.
    report = db_session.get(ReportRunRow, result.report_id)
    assert report is not None
    assert report.pages_rendered >= 6
    total_confidence = sum(report.confidence_summary.values())
    assert total_confidence == len(claims)
    assert "Executive summary" in report.narrative_text
