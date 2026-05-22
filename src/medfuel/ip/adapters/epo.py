"""EPO Open Patent Services (OPS) adapter — REST/XML.

OPS provides bibliographic, claims, and family data for European
patents. Authentication is OAuth2 client credentials; without keys
the adapter is a no-op. The pipeline degrades gracefully so US-only
diligence still works.
"""

from __future__ import annotations

from datetime import UTC, datetime

from medfuel.config import get_settings
from medfuel.db.registry import hash_payload
from medfuel.http.client import RateLimitedClient, RateLimiter
from medfuel.ip.adapters.base import IPSourceAdapter
from medfuel.ip.models import IPSourceType
from medfuel.models.schemas import (
    OFFICIAL_RANK,
    CompanyIdentity,
    JurisdictionScope,
    RawSourceRecord,
)

EPO_BASE = "https://ops.epo.org"
EPO_SEARCH_PATH = "/3.2/rest-services/published-data/search/biblio"


class EPOAdapter(IPSourceAdapter):
    ip_source_type = IPSourceType.EPO
    jurisdiction = "EP"

    def __init__(self, client: RateLimitedClient | None = None, *, api_key: str | None = None):
        settings = get_settings()
        token = api_key if api_key is not None else settings.epo_api_key
        # OPS uses OAuth2; consumers wire a bearer token in via env or kwarg.
        headers: dict[str, str] = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = client or RateLimitedClient(
            base_url=EPO_BASE,
            rate_limiter=RateLimiter(rate_per_second=settings.ema_rate_per_second, burst=2),
            headers=headers,
        )
        self._enabled = bool(token)

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def aclose(self) -> None:
        await self._client.aclose()

    async def discover(
        self,
        identity: CompanyIdentity,
        scope: JurisdictionScope,
    ) -> list[RawSourceRecord]:
        if not self._enabled:
            return []
        params = {"q": f'applicant="{identity.name}"', "Range": "1-25"}
        try:
            data = await self._client.get_json(EPO_SEARCH_PATH, params=params)
        except Exception:
            return []
        entries = (
            data.get("ops:world-patent-data", {})
            .get("ops:biblio-search", {})
            .get("ops:search-result", {})
            .get("ops:publication-reference", [])
        )
        if isinstance(entries, dict):
            entries = [entries]
        out: list[RawSourceRecord] = []
        for entry in entries:
            doc_id = entry.get("document-id") or {}
            country = doc_id.get("country", {}).get("$") or "EP"
            number = doc_id.get("doc-number", {}).get("$")
            kind = doc_id.get("kind", {}).get("$") or ""
            pub = f"{country}{number}{kind}".strip()
            url = f"https://worldwide.espacenet.com/patent/search/publication/{pub}"
            title = f"EPO {pub}"
            out.append(
                RawSourceRecord(
                    source_type=self.source_type,
                    jurisdiction=country,
                    url=url,
                    title=title,
                    payload=entry,
                    published_at=None,
                    retrieved_at=datetime.now(UTC),
                    external_id=pub,
                    content_hash=hash_payload(url, entry, title=title),
                    official_rank=OFFICIAL_RANK[self.source_type],
                )
            )
        return out
