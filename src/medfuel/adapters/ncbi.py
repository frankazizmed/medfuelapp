from __future__ import annotations

from datetime import UTC, datetime

from medfuel.adapters.base import SourceAdapter
from medfuel.config import get_settings
from medfuel.db.registry import hash_payload
from medfuel.http.client import RateLimitedClient, RateLimiter
from medfuel.models.schemas import (
    OFFICIAL_RANK,
    CompanyIdentity,
    JurisdictionScope,
    RawSourceRecord,
    SourceType,
)

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class NCBIAdapter(SourceAdapter):
    """PubMed connector via NCBI E-utilities.

    Without an API key NCBI caps at 3 req/sec; we stay below the no-key ceiling
    by default. With a key, the cap rises to 10 req/sec.
    """

    source_type = SourceType.PUBMED
    jurisdiction = "GLOBAL"

    def __init__(self, client: RateLimitedClient | None = None):
        settings = get_settings()
        rate = 9.0 if settings.ncbi_api_key else settings.ncbi_rate_per_second
        self._client = client or RateLimitedClient(
            base_url=EUTILS_BASE,
            rate_limiter=RateLimiter(rate_per_second=rate, burst=2),
        )
        self._api_key = settings.ncbi_api_key

    async def aclose(self) -> None:
        await self._client.aclose()

    async def discover(
        self,
        identity: CompanyIdentity,
        scope: JurisdictionScope,
    ) -> list[RawSourceRecord]:
        term = f'"{identity.name}"[Affiliation]'
        params = {
            "db": "pubmed",
            "term": term,
            "retmax": 50,
            "retmode": "json",
        }
        if self._api_key:
            params["api_key"] = self._api_key
        try:
            data = await self._client.get_json("/esearch.fcgi", params=params)
        except Exception:
            return []
        ids = (data.get("esearchresult") or {}).get("idlist") or []
        if not ids:
            return []

        summary_params = {
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "json",
        }
        if self._api_key:
            summary_params["api_key"] = self._api_key
        try:
            summary = await self._client.get_json("/esummary.fcgi", params=summary_params)
        except Exception:
            summary = {}
        result = summary.get("result", {}) or {}
        out: list[RawSourceRecord] = []
        for pmid in ids:
            article = result.get(pmid) or {}
            title = article.get("title") or f"PubMed {pmid}"
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            published = _parse_pubdate(article.get("pubdate"))
            payload = {"pmid": pmid, "summary": article}
            out.append(
                RawSourceRecord(
                    source_type=self.source_type,
                    jurisdiction=self.jurisdiction,
                    url=url,
                    title=title,
                    payload=payload,
                    published_at=published,
                    retrieved_at=datetime.now(UTC),
                    external_id=pmid,
                    content_hash=hash_payload(url, payload, title=title),
                    official_rank=OFFICIAL_RANK[self.source_type],
                )
            )
        return out


def _parse_pubdate(value: str | None) -> datetime | None:
    if not value:
        return None
    # PubMed pubdates can be "2024 Mar 15", "2024 Mar", "2024".
    parts = value.split()
    if not parts:
        return None
    try:
        year = int(parts[0])
    except ValueError:
        return None
    return datetime(year, 1, 1, tzinfo=UTC)
