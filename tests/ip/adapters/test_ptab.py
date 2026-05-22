from __future__ import annotations

import httpx
import pytest
import respx

from medfuel.ip.adapters.ptab import PTAB_PATH, PTABAdapter
from medfuel.models.schemas import CompanyIdentity, JurisdictionScope, SourceType


@pytest.mark.asyncio
@respx.mock
async def test_ptab_returns_proceedings():
    respx.get(f"https://developer.uspto.gov{PTAB_PATH}").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "proceedingNumber": "IPR2024-00001",
                        "respondentPatentNumber": "10000001",
                        "proceedingTypeCategory": "Inter Partes Review (IPR)",
                        "petitionerPartyName": "Competitor Inc.",
                        "filingDate": "2024-01-15",
                        "currentStatus": "Instituted",
                    }
                ]
            },
        )
    )
    adapter = PTABAdapter()
    try:
        records = await adapter.discover(
            CompanyIdentity(name="Example Tx"),
            JurisdictionScope(sources=[SourceType.PTAB]),
        )
    finally:
        await adapter.aclose()
    assert len(records) == 1
    assert records[0].source_type == SourceType.PTAB
    assert records[0].external_id == "IPR2024-00001"
