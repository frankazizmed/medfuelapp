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

SEC_BASE = "https://data.sec.gov"


class SECAdapter(SourceAdapter):
    """SEC EDGAR connector via data.sec.gov JSON endpoints.

    SEC requires a descriptive User-Agent with contact info and a programmatic
    ceiling of 10 req/sec; we stay under both.
    """

    source_type = SourceType.SEC
    jurisdiction = "US"

    def __init__(self, client: RateLimitedClient | None = None):
        settings = get_settings()
        self._client = client or RateLimitedClient(
            base_url=SEC_BASE,
            rate_limiter=RateLimiter(rate_per_second=settings.sec_rate_per_second, burst=2),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def discover(
        self,
        identity: CompanyIdentity,
        scope: JurisdictionScope,
    ) -> list[RawSourceRecord]:
        cik = identity.canonical_cik()
        if not cik:
            return []
        records: list[RawSourceRecord] = []
        records.extend(await self._fetch_submissions(cik))
        records.extend(await self._fetch_company_facts(cik))
        return records

    async def _fetch_submissions(self, cik: str) -> list[RawSourceRecord]:
        path = f"/submissions/CIK{cik}.json"
        try:
            data = await self._client.get_json(path)
        except Exception:
            return []
        url = f"{SEC_BASE}{path}"
        recent = (data.get("filings") or {}).get("recent") or {}
        accessions = recent.get("accessionNumber") or []
        forms = recent.get("form") or []
        filing_dates = recent.get("filingDate") or []
        primary_docs = recent.get("primaryDocument") or []
        out: list[RawSourceRecord] = []
        for i, acc in enumerate(accessions):
            form = forms[i] if i < len(forms) else ""
            filing_date = filing_dates[i] if i < len(filing_dates) else None
            doc = primary_docs[i] if i < len(primary_docs) else ""
            filing_payload = {
                "accession": acc,
                "form": form,
                "filingDate": filing_date,
                "primaryDocument": doc,
                "cik": cik,
            }
            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{acc.replace('-', '')}/{doc}"
                if doc
                else url
            )
            out.append(
                RawSourceRecord(
                    source_type=self.source_type,
                    jurisdiction=self.jurisdiction,
                    url=filing_url,
                    title=f"{form} filing {acc}",
                    payload=filing_payload,
                    published_at=_parse_iso_date(filing_date),
                    retrieved_at=datetime.now(UTC),
                    external_id=acc,
                    content_hash=hash_payload(filing_url, filing_payload, title=form),
                    official_rank=OFFICIAL_RANK[self.source_type],
                )
            )
        return out

    async def _fetch_company_facts(self, cik: str) -> list[RawSourceRecord]:
        path = f"/api/xbrl/companyfacts/CIK{cik}.json"
        try:
            data = await self._client.get_json(path)
        except Exception:
            return []
        url = f"{SEC_BASE}{path}"
        title = f"XBRL company facts for CIK {cik}"
        return [
            RawSourceRecord(
                source_type=self.source_type,
                jurisdiction=self.jurisdiction,
                url=url,
                title=title,
                payload={"entityName": data.get("entityName"), "cik": cik},
                retrieved_at=datetime.now(UTC),
                external_id=f"facts-{cik}",
                content_hash=hash_payload(url, data, title=title),
                official_rank=OFFICIAL_RANK[self.source_type],
            )
        ]


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return None
