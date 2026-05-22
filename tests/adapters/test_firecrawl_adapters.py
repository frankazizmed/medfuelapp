from __future__ import annotations

import os

import httpx
import pytest
import respx

from medfuel.adapters.company_web import CompanyWebAdapter
from medfuel.adapters.firecrawl import FirecrawlClient
from medfuel.adapters.mhra import MHRAAdapter
from medfuel.adapters.pmda import PMDAAdapter
from medfuel.config import get_settings
from medfuel.models.schemas import CompanyIdentity, JurisdictionScope, SourceType


@pytest.fixture()
def firecrawl_enabled(monkeypatch):
    monkeypatch.setenv("MEDFUEL_FIRECRAWL_API_KEY", "test-key")
    monkeypatch.setenv("MEDFUEL_FIRECRAWL_BASE_URL", "https://firecrawl.test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_mhra_adapter_no_op_without_firecrawl_key(monkeypatch):
    monkeypatch.delenv("MEDFUEL_FIRECRAWL_API_KEY", raising=False)
    get_settings.cache_clear()  # type: ignore[attr-defined]
    adapter = MHRAAdapter()
    try:
        records = await adapter.discover(
            CompanyIdentity(name="Example Tx"),
            JurisdictionScope(sources=[SourceType.MHRA]),
        )
    finally:
        await adapter.aclose()
    assert records == []
    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.asyncio
@respx.mock
async def test_mhra_adapter_maps_search_results(firecrawl_enabled):
    respx.post("https://firecrawl.test/v2/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "url": "https://products.mhra.gov.uk/product/123",
                        "title": "Examplon SPC",
                    },
                    {
                        "url": "https://www.gov.uk/government/publications/par-examplon",
                        "title": "Examplon PAR",
                    },
                ]
            },
        )
    )

    adapter = MHRAAdapter(firecrawl=FirecrawlClient())
    try:
        records = await adapter.discover(
            CompanyIdentity(name="Example Tx"),
            JurisdictionScope(sources=[SourceType.MHRA]),
        )
    finally:
        await adapter.aclose()
    urls = {str(r.url) for r in records}
    assert any("products.mhra.gov.uk" in u for u in urls)
    assert any("gov.uk/government/publications" in u for u in urls)


@pytest.mark.asyncio
@respx.mock
async def test_pmda_adapter_tags_translation_note(firecrawl_enabled):
    respx.post("https://firecrawl.test/v2/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "url": "https://www.pmda.go.jp/english/review-services/reviews/approved-information/0001.html",
                        "title": "Examplon Review Report",
                    }
                ]
            },
        )
    )
    adapter = PMDAAdapter(firecrawl=FirecrawlClient())
    try:
        records = await adapter.discover(
            CompanyIdentity(name="Example Tx"),
            JurisdictionScope(sources=[SourceType.PMDA]),
        )
    finally:
        await adapter.aclose()
    assert len(records) == 1
    assert "translation_note" in records[0].payload


@pytest.mark.asyncio
@respx.mock
async def test_company_web_adapter_scrapes_known_domains(firecrawl_enabled):
    respx.post("https://firecrawl.test/v2/scrape").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "markdown": "# Pipeline\nExamplon Phase 3 ongoing.",
                    "metadata": {
                        "title": "Example Tx Pipeline",
                        "sourceURL": "https://example.com/pipeline",
                    },
                }
            },
        )
    )
    adapter = CompanyWebAdapter(firecrawl=FirecrawlClient())
    try:
        records = await adapter.discover(
            CompanyIdentity(name="Example Tx", domains=["example.com"]),
            JurisdictionScope(sources=[SourceType.COMPANY]),
        )
    finally:
        await adapter.aclose()
    assert len(records) == 1
    assert records[0].title == "Example Tx Pipeline"
    assert records[0].official_rank > 3  # secondary evidence


# Keep tests below from leaking env mutations across the suite.
@pytest.fixture(autouse=True)
def _clear_settings_cache(monkeypatch):
    yield
    # Reset env vars touched by firecrawl_enabled so other tests see defaults.
    for k in ("MEDFUEL_FIRECRAWL_API_KEY", "MEDFUEL_FIRECRAWL_BASE_URL"):
        if k in os.environ and os.environ[k] in {"test-key", "https://firecrawl.test"}:
            del os.environ[k]
    get_settings.cache_clear()  # type: ignore[attr-defined]
