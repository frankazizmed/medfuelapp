from __future__ import annotations

import httpx
import pytest
import respx

from medfuel.ip.adapters.patentsview import PATENTSVIEW_PATH, PatentsViewAdapter
from medfuel.models.schemas import CompanyIdentity, JurisdictionScope, SourceType


@pytest.mark.asyncio
@respx.mock
async def test_patentsview_returns_records():
    respx.post(f"https://search.patentsview.org{PATENTSVIEW_PATH}").mock(
        return_value=httpx.Response(
            200,
            json={
                "patents": [
                    {
                        "patent_id": "10000001",
                        "patent_number": "10000001",
                        "patent_title": "Antibody composition",
                        "patent_date": "2024-08-01",
                        "patent_num_cited_by_us_patents": 12,
                        "patent_num_us_patent_citations": 30,
                        "assignees": [{"assignee_organization": "Example Tx"}],
                        "claims": [
                            {
                                "claim_number": 1,
                                "claim_text": "A composition comprising X.",
                                "claim_dependent": False,
                            }
                        ],
                    }
                ]
            },
        )
    )

    adapter = PatentsViewAdapter()
    try:
        records = await adapter.discover(
            CompanyIdentity(name="Example Tx"),
            JurisdictionScope(sources=[SourceType.PATENTSVIEW]),
        )
    finally:
        await adapter.aclose()

    assert len(records) == 1
    assert records[0].external_id == "10000001"
    assert records[0].source_type == SourceType.PATENTSVIEW
    assert "patents.google.com" in str(records[0].url)
