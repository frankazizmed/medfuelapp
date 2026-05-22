from __future__ import annotations

import httpx
import pytest
import respx

from medfuel.adapters.fda import FDAAdapter
from medfuel.models.schemas import CompanyIdentity, JurisdictionScope, SourceType


@pytest.mark.asyncio
@respx.mock
async def test_fda_adapter_returns_typed_records():
    respx.get("https://api.fda.gov/drug/label.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "set_id": "abc-123",
                        "openfda": {
                            "brand_name": ["Examplon"],
                            "manufacturer_name": ["Example Tx"],
                        },
                    }
                ]
            },
        )
    )
    respx.get("https://api.fda.gov/device/510k.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "k_number": "K991234",
                        "device_name": "Examplon Stent",
                        "applicant": "Example Tx",
                        "decision_date": "20240115",
                    }
                ]
            },
        )
    )
    respx.get("https://api.fda.gov/drug/drugsfda.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "application_number": "NDA123456",
                        "sponsor_name": "Example Tx",
                        "openfda": {"brand_name": ["Examplon"]},
                    }
                ]
            },
        )
    )

    adapter = FDAAdapter()
    try:
        records = await adapter.discover(
            CompanyIdentity(name="Example Tx"),
            JurisdictionScope(sources=[SourceType.FDA]),
        )
    finally:
        await adapter.aclose()

    by_id = {r.external_id for r in records}
    assert {"abc-123", "K991234", "NDA123456"} <= by_id
    assert all(r.source_type == SourceType.FDA for r in records)
    assert all(r.jurisdiction == "US" for r in records)
    assert all(r.content_hash for r in records)
    k510 = next(r for r in records if r.external_id == "K991234")
    assert k510.published_at is not None
    assert k510.published_at.year == 2024


@pytest.mark.asyncio
@respx.mock
async def test_fda_adapter_swallows_endpoint_errors():
    respx.get("https://api.fda.gov/drug/label.json").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://api.fda.gov/device/510k.json").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    respx.get("https://api.fda.gov/drug/drugsfda.json").mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    adapter = FDAAdapter()
    try:
        records = await adapter.discover(
            CompanyIdentity(name="Example Tx"),
            JurisdictionScope(sources=[SourceType.FDA]),
        )
    finally:
        await adapter.aclose()

    assert records == []
