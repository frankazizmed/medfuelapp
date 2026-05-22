"""Drive the extraction layer across a batch of normalized documents."""

from __future__ import annotations

import asyncio
import logging

from clinical_evidence.config import get_settings
from clinical_evidence.extraction.client import extract_from_text, stub_extract
from clinical_evidence.ingestion.normalizer import normalize
from clinical_evidence.schemas import ClinicalFinding, Publication, RawDocument, Trial

log = logging.getLogger(__name__)


def _link_trial(doc: RawDocument, trials: list[Trial]) -> Trial | None:
    nct = doc.metadata.get("nct_ids") if isinstance(doc.metadata, dict) else None
    if isinstance(nct, list) and nct:
        for t in trials:
            if t.nct_id and t.nct_id in nct:
                return t
    if doc.doc_id.startswith("ct-"):
        nct_id = doc.doc_id.removeprefix("ct-")
        for t in trials:
            if t.nct_id == nct_id:
                return t
    return None


def _link_pub(doc: RawDocument, pubs: list[Publication]) -> Publication | None:
    for p in pubs:
        if p.source_doc_id == doc.doc_id:
            return p
    return None


async def run_extraction(
    *,
    company_id: str,
    documents: list[RawDocument],
    trials: list[Trial],
    publications: list[Publication],
) -> list[ClinicalFinding]:
    settings = get_settings()
    sem = asyncio.Semaphore(settings.max_concurrent_fetches)

    async def _one(doc: RawDocument) -> list[ClinicalFinding]:
        async with sem:
            normalized = normalize(doc)
            trial = _link_trial(normalized, trials)
            pub = _link_pub(normalized, publications)
            kwargs = dict(
                text=normalized.text,
                source=normalized.source.value if hasattr(normalized.source, "value") else str(normalized.source),
                title=normalized.title,
                url=normalized.url,
                company_id=company_id,
                source_doc_id=normalized.doc_id,
                trial_id=trial.trial_id if trial else None,
                pub_id=pub.pub_id if pub else None,
            )
            if settings.openai_api_key:
                return await extract_from_text(**kwargs)
            return stub_extract(**kwargs)

    batches = await asyncio.gather(*[_one(d) for d in documents])
    findings = [f for batch in batches for f in batch]
    log.info("Extraction produced %d findings from %d documents", len(findings), len(documents))
    return findings
