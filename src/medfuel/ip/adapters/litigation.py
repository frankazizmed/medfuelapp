"""Patent litigation adapter.

Surfaces IP litigation tied to the company. Public CourtListener API
exposes a 'recap' patent docket search keyed on party name. The
adapter is a no-op without network access; the verifier handles its
absence by leaving FTO risk at a neutral baseline.
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

COURTLISTENER_BASE = "https://www.courtlistener.com"
DOCKET_SEARCH_PATH = "/api/rest/v3/search/"


class LitigationAdapter(IPSourceAdapter):
    ip_source_type = IPSourceType.LITIGATION
    jurisdiction = "US"

    def __init__(self, client: RateLimitedClient | None = None):
        self._client = client or RateLimitedClient(
            base_url=COURTLISTENER_BASE,
            rate_limiter=RateLimiter(rate_per_second=1.0, burst=2),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def discover(
        self,
        identity: CompanyIdentity,
        scope: JurisdictionScope,
    ) -> list[RawSourceRecord]:
        params = {
            "type": "r",  # recap dockets
            "q": f'"{identity.name}" patent',
            "order_by": "dateFiled desc",
        }
        try:
            data = await self._client.get_json(DOCKET_SEARCH_PATH, params=params)
        except Exception:
            return []
        results = data.get("results") or []
        out: list[RawSourceRecord] = []
        for r in results:
            docket = r.get("docketNumber") or r.get("docket_number") or r.get("id")
            court = r.get("court") or r.get("court_id")
            url = r.get("absolute_url")
            if url and url.startswith("/"):
                url = f"{COURTLISTENER_BASE}{url}"
            if not url:
                continue
            title = r.get("caseName") or r.get("case_name") or f"Docket {docket}"
            out.append(
                RawSourceRecord(
                    source_type=self.source_type,
                    jurisdiction=self.jurisdiction,
                    url=url,
                    title=title,
                    payload=r,
                    published_at=None,
                    retrieved_at=datetime.now(UTC),
                    external_id=str(docket) if docket else None,
                    content_hash=hash_payload(url, r, title=title),
                    official_rank=OFFICIAL_RANK[self.source_type],
                )
            )
            _ = court  # retained on payload; available to verifier
        return out
