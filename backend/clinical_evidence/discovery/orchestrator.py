"""Fan out across discovery sources, dedupe, and return a unified result."""

from __future__ import annotations

import asyncio
import logging

from clinical_evidence.discovery import clinicaltrials, ema, fda, pubmed, sec, tavily
from clinical_evidence.schemas import CompanyContext, DiscoveryResult, Publication, RawDocument, Trial

log = logging.getLogger(__name__)

_SOURCES = (
    ("clinicaltrials", clinicaltrials.fetch),
    ("pubmed", pubmed.fetch),
    ("fda", fda.fetch),
    ("ema", ema.fetch),
    ("sec", sec.fetch),
    ("tavily", tavily.fetch),
)


async def discover(company: CompanyContext) -> DiscoveryResult:
    """Run every source in parallel; merge results."""

    async def _safe(name: str, fn) -> DiscoveryResult:
        try:
            return await fn(company)
        except Exception as exc:  # noqa: BLE001
            log.exception("Discovery source %s failed: %s", name, exc)
            return DiscoveryResult()

    results = await asyncio.gather(*[_safe(name, fn) for name, fn in _SOURCES])

    trials: list[Trial] = []
    pubs: list[Publication] = []
    docs: list[RawDocument] = []
    seen_docs: set[str] = set()
    seen_trials: set[str] = set()
    seen_pubs: set[str] = set()

    for r in results:
        for d in r.documents:
            if d.sha256 in seen_docs:
                continue
            seen_docs.add(d.sha256)
            docs.append(d)
        for t in r.trials:
            key = t.nct_id or t.trial_id
            if key in seen_trials:
                continue
            seen_trials.add(key)
            trials.append(t)
        for p in r.publications:
            key = p.pmid or p.doi or p.pub_id
            if key in seen_pubs:
                continue
            seen_pubs.add(key)
            pubs.append(p)

    log.info(
        "Discovery summary for %s: %d trials, %d publications, %d docs",
        company.name,
        len(trials),
        len(pubs),
        len(docs),
    )
    return DiscoveryResult(trials=trials, publications=pubs, documents=docs)
