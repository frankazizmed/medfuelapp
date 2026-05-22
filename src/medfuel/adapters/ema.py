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

EMA_BASE = "https://www.ema.europa.eu"
# EMA recommends automated consumers fetch the medicines JSON download rather than
# scraping HTML. URL is configurable so the index path can change without a release.
EMA_MEDICINES_JSON_PATH = "/en/medicines/download-medicine-data"


class EMAAdapter(SourceAdapter):
    """EMA medicines connector. Filters the medicines JSON by holder/applicant."""

    source_type = SourceType.EMA
    jurisdiction = "EU"

    def __init__(
        self,
        client: RateLimitedClient | None = None,
        *,
        medicines_url: str | None = None,
    ):
        settings = get_settings()
        self._client = client or RateLimitedClient(
            base_url=EMA_BASE,
            rate_limiter=RateLimiter(rate_per_second=settings.ema_rate_per_second, burst=1),
        )
        self._medicines_url = medicines_url or f"{EMA_BASE}{EMA_MEDICINES_JSON_PATH}"

    async def aclose(self) -> None:
        await self._client.aclose()

    async def discover(
        self,
        identity: CompanyIdentity,
        scope: JurisdictionScope,
    ) -> list[RawSourceRecord]:
        try:
            data = await self._client.get_json(self._medicines_url)
        except Exception:
            return []
        rows = data.get("medicines") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return []
        haystack = {n.lower() for n in [identity.name, *identity.aliases] if n}
        out: list[RawSourceRecord] = []
        for row in rows:
            holder = (row.get("marketing_authorisation_holder") or "").lower()
            applicant = (row.get("applicant") or "").lower()
            if not any(h in holder or h in applicant for h in haystack):
                continue
            url = row.get("url") or self._medicines_url
            title = row.get("name") or row.get("active_substance") or "EMA medicine"
            published = _parse_iso_date(row.get("authorisation_date"))
            out.append(
                RawSourceRecord(
                    source_type=self.source_type,
                    jurisdiction=self.jurisdiction,
                    url=url,
                    title=title,
                    payload=row,
                    published_at=published,
                    retrieved_at=datetime.now(UTC),
                    external_id=row.get("ema_number") or row.get("eu_number"),
                    content_hash=hash_payload(url, row, title=title),
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
