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

# USPTO Open Data Portal (patent applications search).
USPTO_BASE = "https://api.uspto.gov"
USPTO_PATENT_SEARCH_PATH = "/ds-api/oa_actions/v1/records"


class USPTOAdapter(SourceAdapter):
    """USPTO connector keyed on assignee/applicant name.

    The portal exposes multiple datasets; this adapter uses the patent records
    search and is structured so additional datasets (PatentsView, assignments)
    can be added as separate methods without changing the interface.
    """

    source_type = SourceType.USPTO
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
            "criteria": f'patentAssignee:"{identity.name}"',
            "rows": 25,
        }
        try:
            data = await self._client.get_json(USPTO_PATENT_SEARCH_PATH, params=params)
        except Exception:
            return []
        rows = data.get("results") or data.get("response", {}).get("docs") or []
        url = f"{USPTO_BASE}{USPTO_PATENT_SEARCH_PATH}?criteria=patentAssignee:{identity.name}"
        out: list[RawSourceRecord] = []
        for row in rows:
            number = row.get("patentNumber") or row.get("applicationNumber") or row.get("id")
            title = row.get("inventionTitle") or row.get("title") or f"USPTO record {number}"
            published = _parse_iso_date(row.get("patentDate") or row.get("filingDate"))
            row_url = (
                f"https://patents.google.com/patent/US{number}"
                if number and str(number).isdigit()
                else url
            )
            out.append(
                RawSourceRecord(
                    source_type=self.source_type,
                    jurisdiction=self.jurisdiction,
                    url=row_url,
                    title=title,
                    payload=row,
                    published_at=published,
                    retrieved_at=datetime.now(UTC),
                    external_id=str(number) if number else None,
                    content_hash=hash_payload(row_url, row, title=title),
                    official_rank=OFFICIAL_RANK[self.source_type],
                )
            )
        return out


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return None
