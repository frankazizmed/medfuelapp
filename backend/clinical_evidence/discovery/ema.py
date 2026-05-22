"""EMA (European Medicines Agency) source fetcher.

EMA does not publish a stable JSON API for EPARs; we surface the search URL
as a discoverable seed and let Tavily/Firecrawl handle deeper retrieval
when needed. This keeps the island self-contained and avoids brittle
scraping in the discovery layer.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from clinical_evidence.discovery._http import sha256
from clinical_evidence.schemas import CompanyContext, DiscoveryResult, RawDocument, SourceKind

log = logging.getLogger(__name__)


async def fetch(company: CompanyContext) -> DiscoveryResult:
    docs: list[RawDocument] = []
    now = datetime.now(timezone.utc)
    queries: list[str] = [company.name, *company.assets]
    for q in queries:
        url = (
            "https://www.ema.europa.eu/en/search?search_api_fulltext="
            + q.replace(" ", "+")
        )
        body = f"EMA search seed for {q}. Followers should ingest via Firecrawl."
        docs.append(
            RawDocument(
                doc_id=f"ema-seed-{sha256(q)[:12]}",
                company_id=company.company_id,
                source=SourceKind.ema,
                url=url,
                title=f"EMA search: {q}",
                fetched_at=now,
                text=body,
                metadata={"seed": True, "query": q},
                sha256=sha256(body + url),
            )
        )
    log.info("EMA produced %d search seeds for %s", len(docs), company.name)
    return DiscoveryResult(documents=docs)
