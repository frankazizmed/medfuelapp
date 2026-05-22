"""Tavily web search source fetcher.

Used to surface press releases, conference abstracts, company web pages,
and investor decks that aren't in PubMed / ClinicalTrials.gov / FDA / EMA.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from clinical_evidence.config import get_settings
from clinical_evidence.discovery._http import fetch_json, sha256
from clinical_evidence.schemas import CompanyContext, DiscoveryResult, RawDocument, SourceKind

log = logging.getLogger(__name__)

_TAVILY = "https://api.tavily.com/search"

_QUERY_TEMPLATES = [
    "{name} clinical trial results",
    "{name} {asset} efficacy safety phase 3",
    "{name} {asset} adverse events",
    "{name} investor presentation clinical",
    "{name} {asset} {indication} primary endpoint",
    "{name} press release clinical data",
]


def _classify(url: str) -> SourceKind:
    u = url.lower()
    if "investor" in u or "ir." in u:
        return SourceKind.investor_deck
    if "press" in u or "release" in u or "news" in u:
        return SourceKind.press_release
    if "biorxiv" in u or "medrxiv" in u or "preprint" in u:
        return SourceKind.preprint
    if any(c in u for c in ("ash", "asco", "aha", "esmo", "ada", "easd")):
        return SourceKind.conference
    return SourceKind.company_web


async def fetch(company: CompanyContext) -> DiscoveryResult:
    settings = get_settings()
    if not settings.tavily_api_key:
        log.info("Tavily API key not configured; skipping Tavily discovery.")
        return DiscoveryResult()

    queries: list[str] = []
    for tmpl in _QUERY_TEMPLATES:
        for asset in company.assets or [""]:
            for indication in company.indications or [""]:
                q = tmpl.format(
                    name=company.name, asset=asset, indication=indication
                ).replace("  ", " ").strip()
                if q and q not in queries:
                    queries.append(q)

    docs: list[RawDocument] = []
    now = datetime.now(timezone.utc)
    seen_urls: set[str] = set()

    for q in queries[:12]:
        try:
            data = await fetch_json(
                _TAVILY,
                method="POST",
                headers={"Content-Type": "application/json"},
                json_body={
                    "api_key": settings.tavily_api_key,
                    "query": q,
                    "search_depth": "advanced",
                    "max_results": 8,
                    "include_answer": False,
                },
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Tavily search failed for %r: %s", q, exc)
            continue

        for result in (data or {}).get("results", []):
            url = result.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            body = (result.get("content") or "").strip()
            if not body:
                continue
            docs.append(
                RawDocument(
                    doc_id=f"tv-{sha256(url)[:14]}",
                    company_id=company.company_id,
                    source=_classify(url),
                    url=url,
                    title=result.get("title"),
                    fetched_at=now,
                    text=body,
                    metadata={"query": q, "tavily_score": result.get("score")},
                    sha256=sha256(body + url),
                )
            )

    log.info("Tavily returned %d documents for %s", len(docs), company.name)
    return DiscoveryResult(documents=docs)
