from __future__ import annotations

from datetime import UTC, datetime

import pytest

from medfuel.adapters.base import SourceAdapter
from medfuel.db.orm import (
    AssetRow,
    CitationRow,
    ClaimRow,
    RegulatoryEventRow,
    ReportRunRow,
)
from medfuel.db.registry import hash_payload
from medfuel.ingest.pipeline import DiscoveryPipeline, run_discovery
from medfuel.models import (
    CompanyIdentity,
    JurisdictionScope,
    RawSourceRecord,
    SourceType,
)
from medfuel.models.schemas import OFFICIAL_RANK


def _record(source: SourceType, jurisdiction: str, url: str, payload: dict) -> RawSourceRecord:
    return RawSourceRecord(
        source_type=source,
        jurisdiction=jurisdiction,
        url=url,
        title="t",
        payload=payload,
        retrieved_at=datetime.now(UTC),
        content_hash=hash_payload(url, payload, title="t"),
        official_rank=OFFICIAL_RANK[source],
    )


class _FDAStub(SourceAdapter):
    source_type = SourceType.FDA
    jurisdiction = "US"

    def __init__(self, records: list[RawSourceRecord]):
        self._records = records

    async def discover(self, identity, scope):
        return list(self._records)


class _SECStub(SourceAdapter):
    source_type = SourceType.SEC
    jurisdiction = "US"

    def __init__(self, records: list[RawSourceRecord]):
        self._records = records

    async def discover(self, identity, scope):
        return list(self._records)


@pytest.mark.asyncio
async def test_full_pipeline_produces_events_claims_and_report(db_session):
    fda_records = [
        _record(
            SourceType.FDA,
            "US",
            "https://api.fda.gov/device/510k.json?stub=1",
            {
                "k_number": "K991234",
                "device_name": "Examplon Stent",
                "decision_date": "20240115",
                "decision_description": "Substantially Equivalent",
            },
        ),
        _record(
            SourceType.FDA,
            "US",
            "https://api.fda.gov/drug/drugsfda.json?stub=1",
            {
                "application_number": "NDA999",
                "openfda": {"brand_name": ["Examplon"]},
                "submissions": [
                    {
                        "submission_status": "AP",
                        "submission_status_date": "20240301",
                        "submission_class_code": "TYPE 1",
                    }
                ],
            },
        ),
    ]
    sec_records = [
        _record(
            SourceType.SEC,
            "US",
            "https://www.sec.gov/Archives/edgar/data/1/000000-24-000001/example-8k.htm",
            {"form": "8-K", "filingDate": "2024-03-01", "accession": "0000000-24-000001"},
        ),
    ]
    pipeline = DiscoveryPipeline(
        adapters=[_FDAStub(fda_records), _SECStub(sec_records)],
    )

    result = await run_discovery(
        identity=CompanyIdentity(name="Example Tx"),
        scope=JurisdictionScope(sources=[SourceType.FDA, SourceType.SEC]),
        pipeline=pipeline,
        session=db_session,
    )

    assert result.records_persisted_new == 3
    assert result.events_persisted >= 3  # 510k clearance + drugsfda approval + SEC 8-K
    assert result.claims_persisted == result.events_persisted
    assert result.report_id is not None

    # Events landed.
    events = db_session.query(RegulatoryEventRow).all()
    event_types = {e.event_type for e in events}
    assert {"approval", "clearance", "offering_or_filing"} <= event_types

    # Approval/clearance grouped under one asset.
    assets = db_session.query(AssetRow).all()
    assert any("Examplon" in a.asset_name for a in assets)

    # Claims scored and citation table built.
    claims = db_session.query(ClaimRow).all()
    assert claims and all(c.signal_score > 0 for c in claims)

    citations = (
        db_session.query(CitationRow)
        .filter(CitationRow.report_id == result.report_id)
        .all()
    )
    assert citations  # every claim got at least one inline citation

    # Report content has the section template.
    report = db_session.get(ReportRunRow, result.report_id)
    assert report is not None
    assert report.pages_rendered == 4
    assert "Executive summary" in report.narrative_text
    assert "Pathway and timeline" in report.narrative_text
    assert report.confidence_summary["high"] + report.confidence_summary["medium"] >= 1

    # Signal-vs-noise gate ran and is reported in the layout plan.
    noise = report.layout_plan["noise"]
    assert noise["input"] == len(claims)
    assert noise["company_share_cap"] == 0.15
    # Every tier count is accounted for (nothing silently lost).
    accounted = (
        noise["must_include"] + noise["narrative"] + noise["table_only"] + noise["dropped"]
    )
    assert accounted == noise["input"]
