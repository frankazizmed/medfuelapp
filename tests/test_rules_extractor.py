from __future__ import annotations

from datetime import UTC, datetime

import pytest

from medfuel.extract.rules import RuleBasedExtractor
from medfuel.models import RawSourceRecord, SourceType
from medfuel.models.schemas import OFFICIAL_RANK


def _record(source: SourceType, url: str, payload: dict, *, published_at=None) -> RawSourceRecord:
    return RawSourceRecord(
        source_type=source,
        jurisdiction="US",
        url=url,
        title="t",
        payload=payload,
        published_at=published_at,
        retrieved_at=datetime.now(UTC),
        content_hash="h",
        official_rank=OFFICIAL_RANK[source],
    )


@pytest.mark.asyncio
async def test_fda_510k_extracts_clearance_event():
    rec = _record(
        SourceType.FDA,
        "https://api.fda.gov/device/510k.json?...",
        {
            "k_number": "K991234",
            "device_name": "Examplon Stent",
            "decision_date": "20240115",
            "decision_description": "Substantially Equivalent",
        },
    )
    cands = await RuleBasedExtractor().extract(source_doc_id="src_1", record=rec)
    assert len(cands) == 1
    cand = cands[0]
    assert cand.event_type == "clearance"
    assert cand.agency == "FDA"
    assert cand.jurisdiction == "US"
    assert cand.event_date.isoformat() == "2024-01-15"
    assert cand.asset_name == "Examplon Stent"


@pytest.mark.asyncio
async def test_fda_drugsfda_splits_submissions_into_events():
    rec = _record(
        SourceType.FDA,
        "https://api.fda.gov/drug/drugsfda.json?...",
        {
            "application_number": "NDA123456",
            "openfda": {"brand_name": ["Examplon"]},
            "submissions": [
                {
                    "submission_status": "AP",
                    "submission_status_date": "20240301",
                    "submission_class_code": "TYPE 1",
                },
                {
                    "submission_status": "TA",
                    "submission_status_date": "20230101",
                    "submission_class_code": "LABELING",
                },
            ],
        },
    )
    cands = await RuleBasedExtractor().extract(source_doc_id="src_2", record=rec)
    assert {c.event_type for c in cands} == {"approval", "label_change"}
    approval = next(c for c in cands if c.event_type == "approval")
    assert approval.investor_importance == 5


@pytest.mark.asyncio
async def test_sec_filing_maps_to_offering_or_filing():
    rec = _record(
        SourceType.SEC,
        "https://www.sec.gov/Archives/edgar/data/1234567/000123456724000001/example-10k.htm",
        {"form": "10-K", "filingDate": "2024-02-15", "accession": "0001234567-24-000001"},
    )
    cands = await RuleBasedExtractor().extract(source_doc_id="src_3", record=rec)
    assert len(cands) == 1
    assert cands[0].event_type == "offering_or_filing"
    assert cands[0].status == "10-K"


@pytest.mark.asyncio
async def test_ctgov_terminated_trial_is_clinical_hold():
    rec = _record(
        SourceType.CLINICALTRIALS,
        "https://clinicaltrials.gov/study/NCT01",
        {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT01", "briefTitle": "Phase 2"},
                "statusModule": {
                    "overallStatus": "TERMINATED",
                    "lastUpdatePostDateStruct": {"date": "2024-04-01"},
                },
            }
        },
    )
    cands = await RuleBasedExtractor().extract(source_doc_id="src_4", record=rec)
    assert cands[0].event_type == "clinical_hold"
    assert cands[0].status == "TERMINATED"


@pytest.mark.asyncio
async def test_ema_authorisation_is_approval():
    rec = _record(
        SourceType.EMA,
        "https://www.ema.europa.eu/x",
        {"name": "Examplon", "authorisation_date": "2024-05-01"},
    )
    cands = await RuleBasedExtractor().extract(source_doc_id="src_5", record=rec)
    assert cands[0].event_type == "approval"
    assert cands[0].agency == "EMA"
    assert cands[0].jurisdiction == "EU"  # adapter sets jurisdiction; rule respects payload


@pytest.mark.asyncio
async def test_pubmed_records_produce_no_candidates():
    rec = _record(SourceType.PUBMED, "https://pubmed.ncbi.nlm.nih.gov/1/", {"pmid": "1"})
    cands = await RuleBasedExtractor().extract(source_doc_id="src_6", record=rec)
    assert cands == []
