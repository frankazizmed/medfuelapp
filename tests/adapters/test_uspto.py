from __future__ import annotations

import httpx
import pytest
import respx

from medfuel.adapters.uspto import USPTOAdapter
from medfuel.models.schemas import CompanyIdentity, JurisdictionScope, SourceType


@pytest.mark.asyncio
@respx.mock
async def test_uspto_adapter_maps_results():
    respx.get("https://api.uspto.gov/ds-api/oa_actions/v1/records").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "patentNumber": "11111111",
                        "inventionTitle": "Method for Examplon",
                        "patentDate": "2024-08-01",
                    }
                ]
            },
        )
    )

    adapter = USPTOAdapter()
    try:
        records = await adapter.discover(
            CompanyIdentity(name="Example Tx"),
            JurisdictionScope(sources=[SourceType.USPTO]),
        )
    finally:
        await adapter.aclose()

    assert len(records) == 1
    assert records[0].external_id == "11111111"
    assert "patents.google.com" in str(records[0].url)
    assert records[0].published_at is not None
