from __future__ import annotations

from datetime import UTC, datetime

from medfuel.adapters.base import SourceAdapter
from medfuel.adapters.firecrawl import FirecrawlClient
from medfuel.db.registry import hash_payload
from medfuel.models.schemas import (
    OFFICIAL_RANK,
    CompanyIdentity,
    JurisdictionScope,
    RawSourceRecord,
    SourceType,
)


class PMDAAdapter(SourceAdapter):
    """PMDA English review-reports connector via Firecrawl search.

    PMDA's English pages are convenience translations; the Japanese original
    prevails. Downstream consumers should tag PMDA-derived English claims as
    'translated official source' unless independently corroborated.
    """

    source_type = SourceType.PMDA
    jurisdiction = "JP"

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
        query = f'site:pmda.go.jp/english "{identity.name}" review report'
        try:
            data = await self._firecrawl.search(query, limit=15)
        except Exception:
            return []
        hits = data.get("data") or data.get("results") or []
        out: list[RawSourceRecord] = []
        for h in hits:
            url = h.get("url") or h.get("link")
            if not url:
                continue
            title = h.get("title") or "PMDA result"
            payload = {**h, "translation_note": "PMDA English is a convenience translation"}
            out.append(
                RawSourceRecord(
                    source_type=self.source_type,
                    jurisdiction=self.jurisdiction,
                    url=url,
                    title=title,
                    payload=payload,
                    retrieved_at=datetime.now(UTC),
                    content_hash=hash_payload(url, payload, title=title),
                    official_rank=OFFICIAL_RANK[self.source_type],
                )
            )
        return out
