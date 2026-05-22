"""PatentsView API adapter.

PatentsView is USPTO's bulk-grade patent data service: structured
patent + claim + assignee + citation tables. Queries are POST JSON to
the new search endpoint with a CQL-like filter.

Public docs: https://search.patentsview.org/docs/
"""

from __future__ import annotations

from datetime import UTC, datetime

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

PATENTSVIEW_BASE = "https://search.patentsview.org"
PATENTSVIEW_PATH = "/api/v1/patent/"


class PatentsViewAdapter(IPSourceAdapter):
    """Query PatentsView for granted patents tied to the assignee name."""

    ip_source_type = IPSourceType.PATENTSVIEW
    jurisdiction = "US"

    def __init__(self, client: RateLimitedClient | None = None):
        self._client = client or RateLimitedClient(
            base_url=PATENTSVIEW_BASE,
            rate_limiter=RateLimiter(rate_per_second=2.0, burst=2),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def discover(
        self,
        identity: CompanyIdentity,
        scope: JurisdictionScope,
    ) -> list[RawSourceRecord]:
        names = [identity.name, *identity.aliases]
        query = {
            "_or": [{"assignees.assignee_organization": n} for n in names if n]
        }
        body = {
            "q": query,
            "f": [
                "patent_id",
                "patent_number",
                "patent_title",
                "patent_date",
                "patent_kind",
                "application.filing_date",
                "earliest_priority_date",
                "assignees.assignee_organization",
                "inventors.inventor_name_first",
                "inventors.inventor_name_last",
                "cpc_current.cpc_subclass_id",
                "claims.claim_number",
                "claims.claim_text",
                "claims.claim_dependent",
                "patent_num_us_patent_citations",
                "patent_num_cited_by_us_patents",
            ],
            "o": {"per_page": 25},
        }
        try:
            resp = await self._client.request("POST", PATENTSVIEW_PATH, json=body)
            data = resp.json()
        except Exception:
            return []
        patents = data.get("patents") or []
        out: list[RawSourceRecord] = []
        for p in patents:
            pub = p.get("patent_number") or p.get("patent_id")
            url = f"https://patents.google.com/patent/US{pub}" if pub else PATENTSVIEW_BASE
            title = p.get("patent_title") or f"PatentsView {pub}"
            out.append(
                RawSourceRecord(
                    source_type=self.source_type,
                    jurisdiction=self.jurisdiction,
                    url=url,
                    title=title,
                    payload=p,
                    published_at=_iso(p.get("patent_date")),
                    retrieved_at=datetime.now(UTC),
                    external_id=str(pub) if pub else None,
                    content_hash=hash_payload(url, p, title=title),
                    official_rank=OFFICIAL_RANK[self.source_type],
                )
            )
        return out


def _iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return None
