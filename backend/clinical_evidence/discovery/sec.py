"""SEC EDGAR filings source fetcher.

Looks up the company's CIK via the public ticker index, then pulls recent
10-K / 10-Q / 8-K filings. Filing text is fetched and stored as
RawDocument so downstream extraction can pull clinical disclosures.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from clinical_evidence.config import get_settings
from clinical_evidence.discovery._http import fetch_json, fetch_text, sha256
from clinical_evidence.schemas import CompanyContext, DiscoveryResult, RawDocument, SourceKind

log = logging.getLogger(__name__)

_TICKERS = "https://www.sec.gov/files/company_tickers.json"
_FORM_TYPES = ("10-K", "10-Q", "8-K")


async def _lookup_cik(tickers: list[str]) -> list[str]:
    if not tickers:
        return []
    settings = get_settings()
    headers = {"User-Agent": settings.sec_user_agent}
    try:
        idx = await fetch_json(_TICKERS, headers=headers)
    except Exception as exc:  # noqa: BLE001
        log.warning("SEC ticker index fetch failed: %s", exc)
        return []
    wanted = {t.upper() for t in tickers}
    ciks: list[str] = []
    for entry in (idx or {}).values():
        if entry.get("ticker", "").upper() in wanted:
            ciks.append(str(entry.get("cik_str", "")).zfill(10))
    return ciks


async def fetch(company: CompanyContext) -> DiscoveryResult:
    settings = get_settings()
    headers = {"User-Agent": settings.sec_user_agent}

    ciks = await _lookup_cik(company.tickers)
    if not ciks:
        return DiscoveryResult()

    docs: list[RawDocument] = []
    now = datetime.now(timezone.utc)

    for cik in ciks:
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        try:
            data = await fetch_json(url, headers=headers)
        except Exception as exc:  # noqa: BLE001
            log.warning("SEC submissions fetch failed for CIK %s: %s", cik, exc)
            continue

        recent = (data.get("filings", {}) or {}).get("recent", {})
        forms = recent.get("form", []) or []
        accessions = recent.get("accessionNumber", []) or []
        dates = recent.get("filingDate", []) or []
        docs_recent = recent.get("primaryDocument", []) or []

        for form, acc, date, primary in zip(forms, accessions, dates, docs_recent):
            if form not in _FORM_TYPES:
                continue
            acc_nodash = acc.replace("-", "")
            file_url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash}/{primary}"
            )
            try:
                text = await fetch_text(file_url, headers=headers)
            except Exception as exc:  # noqa: BLE001
                log.warning("SEC filing fetch failed (%s): %s", file_url, exc)
                continue
            docs.append(
                RawDocument(
                    doc_id=f"sec-{cik}-{acc_nodash}",
                    company_id=company.company_id,
                    source=SourceKind.sec,
                    url=file_url,
                    title=f"{form} filing {date}",
                    fetched_at=now,
                    text=text[:1_500_000],  # cap to keep DB sane
                    metadata={"cik": cik, "form": form, "filing_date": date},
                    sha256=sha256(text),
                )
            )

    log.info("SEC EDGAR returned %d filings for %s", len(docs), company.name)
    return DiscoveryResult(documents=docs)
