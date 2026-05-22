from __future__ import annotations

import httpx
import pytest
import respx

from medfuel.adapters.ema import EMAAdapter
from medfuel.models.schemas import CompanyIdentity, JurisdictionScope, SourceType


@pytest.mark.asyncio
@respx.mock
async def test_ema_adapter_filters_medicines_by_holder():
    medicines_url = "https://example.test/medicines.json"
    respx.get(medicines_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "medicines": [
                    {
                        "name": "Examplon",
                        "marketing_authorisation_holder": "Example Tx Europe BV",
                        "url": "https://www.ema.europa.eu/en/medicines/human/EPAR/examplon",
                        "ema_number": "EU/1/24/9999",
                        "authorisation_date": "2024-05-01",
                    },
                    {
                        "name": "Other Drug",
                        "marketing_authorisation_holder": "Unrelated AG",
                        "url": "https://www.ema.europa.eu/x/other",
                    },
                ]
            },
        )
    )

    adapter = EMAAdapter(medicines_url=medicines_url)
    try:
        records = await adapter.discover(
            CompanyIdentity(name="Example Tx"),
            JurisdictionScope(sources=[SourceType.EMA]),
        )
    finally:
        await adapter.aclose()

    assert len(records) == 1
    assert records[0].external_id == "EU/1/24/9999"
    assert records[0].jurisdiction == "EU"
    assert records[0].published_at is not None
