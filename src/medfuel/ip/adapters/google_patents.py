"""Google Patents adapter via Firecrawl search/scrape.

Google Patents has no public structured API; the adapter discovers
results via Firecrawl's /v2/search and scrapes individual records when
useful. Without a Firecrawl key, the adapter is a no-op so the rest of
the IP pipeline keeps running offline.
"""

from __future__ import annotations

from datetime import UTC, datetime

from medfuel.adapters.firecrawl import FirecrawlClient
from medfuel.db.registry import hash_payload
from medfuel.ip.adapters.base import IPSourceAdapter
from medfuel.ip.models import IPSourceType
from medfuel.models.schemas import (
    OFFICIAL_RANK,
    CompanyIdentity,
    JurisdictionScope,
    RawSourceRecord,
)


class GooglePatentsAdapter(IPSourceAdapter):
    ip_source_type = IPSourceType.GOOGLE_PATENTS
    jurisdiction = "GLOBAL"

    def __init__(self, firecrawl: FirecrawlClient | None = None):
        self._firecrawl = firecrawl or FirecrawlClient()

    async def aclose(self) -> None:
        await self._firecrawl.aclose()

    async def discover(
        self,
        identity: CompanyIdentity,
        scope: JurisdictionScope,
    ) -> list[RawSourceRecord]:
        if not self._firecrawl.enabled:
            return []
        query = f'site:patents.google.com "{identity.name}" assignee'
        try:
            data = await self._firecrawl.search(query, limit=20)
        except Exception:
            return []
        hits = data.get("data") or data.get("results") or []
        out: list[RawSourceRecord] = []
        for hit in hits:
            url = hit.get("url") or hit.get("link")
            if not url or "patents.google.com" not in url:
                continue
            payload = {
                "title": hit.get("title"),
                "description": hit.get("description") or hit.get("snippet"),
                "url": url,
            }
            out.append(
                RawSourceRecord(
                    source_type=self.source_type,
                    jurisdiction=self.jurisdiction,
                    url=url,
                    title=hit.get("title") or url,
                    payload=payload,
                    published_at=None,
                    retrieved_at=datetime.now(UTC),
                    external_id=_id_from_url(url),
                    content_hash=hash_payload(url, payload, title=payload["title"]),
                    official_rank=OFFICIAL_RANK[self.source_type],
                )
            )
        return out


def _id_from_url(url: str) -> str | None:
    # https://patents.google.com/patent/US1234567B2/en → US1234567B2
    parts = url.rstrip("/").split("/")
    if "patent" in parts:
        idx = parts.index("patent")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None
