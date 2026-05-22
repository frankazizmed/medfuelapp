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


class CompanyWebAdapter(SourceAdapter):
    """Company website + IR/pipeline pages via Firecrawl scrape.

    Treated as secondary evidence by design: official_rank is intentionally
    lower than regulator sources so downstream verification can prefer
    regulator records when they conflict with company claims.
    """

    source_type = SourceType.COMPANY
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
        if not self._firecrawl.enabled or not identity.domains:
            return []
        out: list[RawSourceRecord] = []
        for domain in identity.domains:
            base_url = domain if domain.startswith("http") else f"https://{domain}"
            try:
                data = await self._firecrawl.scrape(base_url, formats=["markdown"])
            except Exception:
                continue
            page = data.get("data") or data
            content = page.get("markdown") or page.get("content") or ""
            metadata = page.get("metadata") or {}
            title = metadata.get("title") or domain
            payload = {"metadata": metadata, "content_snippet": content[:4000]}
            out.append(
                RawSourceRecord(
                    source_type=self.source_type,
                    jurisdiction=self.jurisdiction,
                    url=metadata.get("sourceURL") or base_url,
                    title=title,
                    payload=payload,
                    retrieved_at=datetime.now(UTC),
                    content_hash=hash_payload(base_url, payload, title=title),
                    official_rank=OFFICIAL_RANK[self.source_type],
                )
            )
        return out
