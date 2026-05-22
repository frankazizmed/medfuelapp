from __future__ import annotations

from medfuel.config import get_settings
from medfuel.http.client import RateLimitedClient, RateLimiter


class FirecrawlClient:
    """Thin wrapper over Firecrawl's v2 HTTP API.

    Routing convention (per design):
      - Public HTML/PDF URL: POST /v2/scrape
      - Local upload / non-public file: POST /v2/parse
      - Many pages under one domain: POST /v2/crawl
      - Discovery: POST /v2/search

    The wrapper is intentionally minimal; adapters compose these calls.
    """

    def __init__(self, client: RateLimitedClient | None = None):
        settings = get_settings()
        headers: dict[str, str] = {}
        if settings.firecrawl_api_key:
            headers["Authorization"] = f"Bearer {settings.firecrawl_api_key}"
        self._client = client or RateLimitedClient(
            base_url=settings.firecrawl_base_url,
            rate_limiter=RateLimiter(
                rate_per_second=settings.firecrawl_rate_per_second, burst=2
            ),
            headers=headers,
        )
        self._enabled = bool(settings.firecrawl_api_key)

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def aclose(self) -> None:
        await self._client.aclose()

    async def scrape(self, url: str, **options) -> dict:
        body = {"url": url, **options}
        resp = await self._client.request("POST", "/v2/scrape", json=body)
        resp.raise_for_status()
        return resp.json()

    async def search(self, query: str, *, limit: int = 10, **options) -> dict:
        body = {"query": query, "limit": limit, **options}
        resp = await self._client.request("POST", "/v2/search", json=body)
        resp.raise_for_status()
        return resp.json()

    async def crawl(self, url: str, *, limit: int = 50, **options) -> dict:
        body = {"url": url, "limit": limit, **options}
        resp = await self._client.request("POST", "/v2/crawl", json=body)
        resp.raise_for_status()
        return resp.json()

    async def parse(self, *, url: str | None = None, file_b64: str | None = None, **options) -> dict:
        body: dict = {**options}
        if url:
            body["url"] = url
        if file_b64:
            body["file"] = file_b64
        resp = await self._client.request("POST", "/v2/parse", json=body)
        resp.raise_for_status()
        return resp.json()
