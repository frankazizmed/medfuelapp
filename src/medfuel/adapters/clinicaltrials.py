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

CTGOV_BASE = "https://clinicaltrials.gov/api/v2"
PAGE_SIZE = 200  # below the 1,000-study cap to keep per-page latency predictable.


class ClinicalTrialsAdapter(SourceAdapter):
    """ClinicalTrials.gov v2 connector keyed off sponsor name."""

    source_type = SourceType.CLINICALTRIALS
    jurisdiction = "GLOBAL"

    def __init__(self, client: RateLimitedClient | None = None):
        settings = get_settings()
        self._client = client or RateLimitedClient(
            base_url=CTGOV_BASE,
            rate_limiter=RateLimiter(
                rate_per_second=settings.clinicaltrials_rate_per_second, burst=2
            ),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def discover(
        self,
        identity: CompanyIdentity,
        scope: JurisdictionScope,
    ) -> list[RawSourceRecord]:
        results: list[RawSourceRecord] = []
        names = [identity.name, *identity.aliases]
        for name in names:
            results.extend(await self._search_sponsor(name))
        return results

    async def _search_sponsor(self, name: str) -> list[RawSourceRecord]:
        params = {
            "query.spons": name,
            "pageSize": PAGE_SIZE,
            "format": "json",
        }
        try:
            data = await self._client.get_json("/studies", params=params)
        except Exception:
            return []
        studies = data.get("studies", [])
        url = f"{CTGOV_BASE}/studies?query.spons={name}"
        out: list[RawSourceRecord] = []
        for study in studies:
            protocol = study.get("protocolSection", {}) or {}
            ident = protocol.get("identificationModule", {}) or {}
            status = protocol.get("statusModule", {}) or {}
            nct_id = ident.get("nctId")
            title = ident.get("briefTitle") or nct_id or "Clinical study"
            study_url = (
                f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else url
            )
            published = _parse_iso_date(status.get("lastUpdatePostDateStruct", {}).get("date"))
            out.append(
                RawSourceRecord(
                    source_type=self.source_type,
                    jurisdiction=self.jurisdiction,
                    url=study_url,
                    title=title,
                    payload=study,
                    published_at=published,
                    retrieved_at=datetime.now(UTC),
                    external_id=nct_id,
                    content_hash=hash_payload(study_url, study, title=title),
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
