from __future__ import annotations

import httpx
import pytest
import respx

from medfuel.adapters.ncbi import NCBIAdapter
from medfuel.models.schemas import CompanyIdentity, JurisdictionScope, SourceType


@pytest.mark.asyncio
@respx.mock
async def test_ncbi_adapter_combines_esearch_and_esummary():
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
        return_value=httpx.Response(
            200,
            json={"esearchresult": {"idlist": ["111", "222"]}},
        )
    )
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "111": {"title": "Examplon mechanism", "pubdate": "2023 Mar"},
                    "222": {"title": "Examplon trial follow-up", "pubdate": "2024"},
                }
            },
        )
    )

    adapter = NCBIAdapter()
    try:
        records = await adapter.discover(
            CompanyIdentity(name="Example Tx"),
            JurisdictionScope(sources=[SourceType.PUBMED]),
        )
    finally:
        await adapter.aclose()

    assert {r.external_id for r in records} == {"111", "222"}
    assert all("pubmed.ncbi.nlm.nih.gov" in str(r.url) for r in records)


@pytest.mark.asyncio
@respx.mock
async def test_ncbi_adapter_returns_empty_when_no_hits():
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
        return_value=httpx.Response(200, json={"esearchresult": {"idlist": []}})
    )
    adapter = NCBIAdapter()
    try:
        records = await adapter.discover(
            CompanyIdentity(name="Example Tx"),
            JurisdictionScope(sources=[SourceType.PUBMED]),
        )
    finally:
        await adapter.aclose()
    assert records == []
