from __future__ import annotations

import httpx
import pytest
import respx

from medfuel.adapters.sec import SECAdapter
from medfuel.models.schemas import CompanyIdentity, JurisdictionScope, SourceType


@pytest.mark.asyncio
@respx.mock
async def test_sec_adapter_pads_cik_and_builds_filing_records():
    respx.get("https://data.sec.gov/submissions/CIK0001234567.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "entityName": "Example Tx",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001234567-24-000001"],
                        "form": ["10-K"],
                        "filingDate": ["2024-02-15"],
                        "primaryDocument": ["example-10k.htm"],
                    }
                },
            },
        )
    )
    respx.get("https://data.sec.gov/api/xbrl/companyfacts/CIK0001234567.json").mock(
        return_value=httpx.Response(
            200, json={"entityName": "Example Tx", "facts": {}}
        )
    )

    adapter = SECAdapter()
    try:
        records = await adapter.discover(
            CompanyIdentity(name="Example Tx", cik="1234567"),
            JurisdictionScope(sources=[SourceType.SEC]),
        )
    finally:
        await adapter.aclose()

    filing = next(r for r in records if r.external_id == "0001234567-24-000001")
    assert "Archives/edgar/data/1234567" in str(filing.url)
    assert "example-10k.htm" in str(filing.url)
    assert filing.published_at is not None and filing.published_at.year == 2024
    assert any(r.external_id == "facts-0001234567" for r in records)


@pytest.mark.asyncio
async def test_sec_adapter_skips_when_cik_missing():
    adapter = SECAdapter()
    try:
        records = await adapter.discover(
            CompanyIdentity(name="Example Tx"),
            JurisdictionScope(sources=[SourceType.SEC]),
        )
    finally:
        await adapter.aclose()
    assert records == []
