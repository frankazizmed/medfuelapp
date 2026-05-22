from __future__ import annotations

import httpx
import pytest
import respx

from medfuel.adapters.clinicaltrials import ClinicalTrialsAdapter
from medfuel.models.schemas import CompanyIdentity, JurisdictionScope, SourceType


@pytest.mark.asyncio
@respx.mock
async def test_ctgov_adapter_maps_studies_to_records():
    respx.get("https://clinicaltrials.gov/api/v2/studies").mock(
        return_value=httpx.Response(
            200,
            json={
                "studies": [
                    {
                        "protocolSection": {
                            "identificationModule": {
                                "nctId": "NCT01234567",
                                "briefTitle": "A Phase 2 Trial of Examplon",
                            },
                            "statusModule": {
                                "lastUpdatePostDateStruct": {"date": "2025-03-01"},
                            },
                        }
                    }
                ]
            },
        )
    )

    adapter = ClinicalTrialsAdapter()
    try:
        records = await adapter.discover(
            CompanyIdentity(name="Example Tx"),
            JurisdictionScope(sources=[SourceType.CLINICALTRIALS]),
        )
    finally:
        await adapter.aclose()

    assert len(records) == 1
    rec = records[0]
    assert rec.external_id == "NCT01234567"
    assert "clinicaltrials.gov/study/NCT01234567" in str(rec.url)
    assert rec.published_at is not None and rec.published_at.year == 2025
