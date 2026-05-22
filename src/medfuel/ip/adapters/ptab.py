"""PTAB proceedings adapter.

Pulls Inter Partes Review (IPR), Post-Grant Review (PGR), and Covered
Business Method (CBM) proceedings tied to the company's patents from
USPTO's PTAB Open Data API. PTAB exposure is a first-class FTO and
defensibility signal.
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

PTAB_BASE = "https://developer.uspto.gov"
PTAB_PATH = "/ptab-api/proceedings"


class PTABAdapter(IPSourceAdapter):
    ip_source_type = IPSourceType.PTAB
    jurisdiction = "US"

    def __init__(self, client: RateLimitedClient | None = None):
        settings = get_settings()
        self._client = client or RateLimitedClient(
            base_url=PTAB_BASE,
            rate_limiter=RateLimiter(rate_per_second=settings.uspto_rate_per_second, burst=2),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def discover(
        self,
        identity: CompanyIdentity,
        scope: JurisdictionScope,
    ) -> list[RawSourceRecord]:
        params = {
            "partyName": identity.name,
            "recordTotalQuantity": 25,
        }
        try:
            data = await self._client.get_json(PTAB_PATH, params=params)
        except Exception:
            return []
        rows = data.get("results") or []
        out: list[RawSourceRecord] = []
        for row in rows:
            proc_id = row.get("proceedingNumber") or row.get("id")
            patent = row.get("respondentPatentNumber") or row.get("patentNumber")
            url = (
                f"https://acts.uspto.gov/oss-web/searchOSS#/proceedings/{proc_id}"
                if proc_id else PTAB_BASE
            )
            title = f"PTAB {proc_id} (patent {patent or 'unknown'})"
            out.append(
                RawSourceRecord(
                    source_type=self.source_type,
                    jurisdiction=self.jurisdiction,
                    url=url,
                    title=title,
                    payload=row,
                    published_at=None,
                    retrieved_at=datetime.now(UTC),
                    external_id=str(proc_id) if proc_id else None,
                    content_hash=hash_payload(url, row, title=title),
                    official_rank=OFFICIAL_RANK[self.source_type],
                )
            )
        return out
