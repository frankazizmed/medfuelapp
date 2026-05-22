"""USPTO assignment search adapter.

The USPTO assignment dataset exposes the chain of title for every
recorded assignment. Diligence cares about: (a) is the assignee on the
patent actually the company under review, (b) any sale/license events
hidden in chain-of-title, (c) lien recordings.

The adapter targets the USPTO Open Data Portal assignment dataset; if
the dataset is unreachable it returns []. The verifier uses any
returned records to upgrade family-level confidence.
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

USPTO_BASE = "https://api.uspto.gov"
ASSIGNMENT_PATH = "/ds-api/assignment/v1/records"


class USPTOAssignmentAdapter(IPSourceAdapter):
    ip_source_type = IPSourceType.USPTO_ASSIGNMENT
    jurisdiction = "US"

    def __init__(self, client: RateLimitedClient | None = None):
        settings = get_settings()
        headers: dict[str, str] = {}
        if settings.uspto_api_key:
            headers["X-API-KEY"] = settings.uspto_api_key
        self._client = client or RateLimitedClient(
            base_url=USPTO_BASE,
            rate_limiter=RateLimiter(rate_per_second=settings.uspto_rate_per_second, burst=2),
            headers=headers,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def discover(
        self,
        identity: CompanyIdentity,
        scope: JurisdictionScope,
    ) -> list[RawSourceRecord]:
        params = {
            "criteria": f'assigneeName:"{identity.name}" OR assignorName:"{identity.name}"',
            "rows": 25,
        }
        try:
            data = await self._client.get_json(ASSIGNMENT_PATH, params=params)
        except Exception:
            return []
        rows = data.get("results") or data.get("response", {}).get("docs") or []
        out: list[RawSourceRecord] = []
        for row in rows:
            reel_frame = row.get("reelFrame") or row.get("id")
            patent = row.get("patentNumber") or row.get("applicationNumber")
            url = (
                f"https://assignment.uspto.gov/patent/index.html#/patent/search/resultAssignment"
                f"?id={reel_frame}"
            )
            title = f"USPTO assignment {reel_frame} ({patent or 'no-patent'})"
            out.append(
                RawSourceRecord(
                    source_type=self.source_type,
                    jurisdiction=self.jurisdiction,
                    url=url,
                    title=title,
                    payload=row,
                    published_at=None,
                    retrieved_at=datetime.now(UTC),
                    external_id=str(reel_frame) if reel_frame else None,
                    content_hash=hash_payload(url, row, title=title),
                    official_rank=OFFICIAL_RANK[self.source_type],
                )
            )
        return out
