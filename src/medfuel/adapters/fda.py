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

OPENFDA_BASE = "https://api.fda.gov"


class FDAAdapter(SourceAdapter):
    """openFDA connector covering drug labels, 510(k), and Drugs@FDA records.

    Rate ceiling is 240 req/min (120,000/day) per API key; we run below that.
    """

    source_type = SourceType.FDA
    jurisdiction = "US"

    def __init__(self, client: RateLimitedClient | None = None):
        settings = get_settings()
        self._client = client or RateLimitedClient(
            base_url=OPENFDA_BASE,
            rate_limiter=RateLimiter.per_minute(settings.openfda_rate_per_minute, burst=4),
        )
        self._api_key = settings.openfda_api_key

    async def aclose(self) -> None:
        await self._client.aclose()

    async def discover(
        self,
        identity: CompanyIdentity,
        scope: JurisdictionScope,
    ) -> list[RawSourceRecord]:
        names = [identity.name, *identity.aliases]
        records: list[RawSourceRecord] = []
        seen_hashes: set[str] = set()

        for name in names:
            records.extend(await self._fetch_drug_labels(name, seen_hashes))
            records.extend(await self._fetch_device_510k(name, seen_hashes))
            records.extend(await self._fetch_drugs_at_fda(name, seen_hashes))
        return records

    # ---------------------------------------------------------------- queries
    async def _fetch_drug_labels(self, name: str, seen: set[str]) -> list[RawSourceRecord]:
        params = {
            "search": f'openfda.manufacturer_name:"{name}"',
            "limit": 25,
        }
        if self._api_key:
            params["api_key"] = self._api_key
        try:
            data = await self._client.get_json("/drug/label.json", params=params)
        except Exception:
            return []
        return self._records_from_results(
            results=data.get("results", []),
            endpoint="/drug/label.json",
            params=params,
            title_factory=lambda r: r.get("openfda", {}).get("brand_name", ["unknown"])[0]
            if r.get("openfda")
            else "Drug Label",
            external_id_field="set_id",
            seen=seen,
        )

    async def _fetch_device_510k(self, name: str, seen: set[str]) -> list[RawSourceRecord]:
        params = {
            "search": f'applicant:"{name}"',
            "limit": 25,
        }
        if self._api_key:
            params["api_key"] = self._api_key
        try:
            data = await self._client.get_json("/device/510k.json", params=params)
        except Exception:
            return []
        return self._records_from_results(
            results=data.get("results", []),
            endpoint="/device/510k.json",
            params=params,
            title_factory=lambda r: r.get("device_name") or r.get("k_number") or "510(k)",
            external_id_field="k_number",
            seen=seen,
            published_field="decision_date",
        )

    async def _fetch_drugs_at_fda(self, name: str, seen: set[str]) -> list[RawSourceRecord]:
        params = {
            "search": f'sponsor_name:"{name}"',
            "limit": 25,
        }
        if self._api_key:
            params["api_key"] = self._api_key
        try:
            data = await self._client.get_json("/drug/drugsfda.json", params=params)
        except Exception:
            return []
        return self._records_from_results(
            results=data.get("results", []),
            endpoint="/drug/drugsfda.json",
            params=params,
            title_factory=lambda r: r.get("openfda", {}).get("brand_name", [r.get("application_number", "Drugs@FDA")])[0]
            if r.get("openfda")
            else r.get("application_number", "Drugs@FDA"),
            external_id_field="application_number",
            seen=seen,
        )

    # --------------------------------------------------------------- helpers
    def _records_from_results(
        self,
        *,
        results: list[dict],
        endpoint: str,
        params: dict,
        title_factory,
        external_id_field: str,
        seen: set[str],
        published_field: str | None = None,
    ) -> list[RawSourceRecord]:
        url = self._url(endpoint, params)
        out: list[RawSourceRecord] = []
        for r in results:
            content_hash = hash_payload(url, r, title=str(r.get(external_id_field)))
            if content_hash in seen:
                continue
            seen.add(content_hash)
            out.append(
                RawSourceRecord(
                    source_type=self.source_type,
                    jurisdiction=self.jurisdiction,
                    url=url,
                    title=str(title_factory(r)),
                    payload=r,
                    published_at=_parse_date(r.get(published_field)) if published_field else None,
                    retrieved_at=datetime.now(UTC),
                    external_id=str(r.get(external_id_field)) if r.get(external_id_field) else None,
                    content_hash=content_hash,
                    official_rank=OFFICIAL_RANK[self.source_type],
                )
            )
        return out

    @staticmethod
    def _url(endpoint: str, params: dict) -> str:
        query = "&".join(f"{k}={v}" for k, v in params.items() if k != "api_key")
        return f"{OPENFDA_BASE}{endpoint}?{query}"


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    # openFDA dates are typically YYYYMMDD or YYYY-MM-DD.
    raw = value.replace("-", "")
    if len(raw) != 8 or not raw.isdigit():
        return None
    return datetime(int(raw[:4]), int(raw[4:6]), int(raw[6:8]), tzinfo=UTC)
