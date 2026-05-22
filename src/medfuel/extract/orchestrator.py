from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy.orm import Session

from medfuel.db.orm import ExtractionRow, SourceDocumentRow
from medfuel.extract.base import Extractor
from medfuel.extract.rules import RuleBasedExtractor
from medfuel.models import CandidateEvent, RawSourceRecord, SourceType

log = logging.getLogger(__name__)


class ExtractionOrchestrator:
    """Run all configured extractors over a company's source documents."""

    def __init__(self, extractors: list[Extractor] | None = None):
        self._extractors = extractors or [RuleBasedExtractor()]

    async def run(
        self,
        *,
        session: Session,
        company_id: str,
        job_id: str | None,
    ) -> list[tuple[str, CandidateEvent]]:
        """Return (source_doc_id, candidate) pairs and persist raw extractions for audit."""
        docs = (
            session.query(SourceDocumentRow)
            .filter(SourceDocumentRow.company_id == company_id)
            .all()
        )
        results = await asyncio.gather(*[self._extract_one(doc) for doc in docs])
        pairs: list[tuple[str, CandidateEvent]] = []
        for doc, cands in zip(docs, results, strict=True):
            for cand in cands:
                pairs.append((doc.source_doc_id, cand))
            if cands:
                session.add(
                    ExtractionRow(
                        extraction_id=f"ext_{uuid.uuid4().hex[:12]}",
                        job_id=job_id,
                        source_doc_id=doc.source_doc_id,
                        extractor=cands[0].extractor,
                        payload={"candidates": [c.model_dump(mode="json") for c in cands]},
                    )
                )
        session.flush()
        return pairs

    async def _extract_one(self, doc: SourceDocumentRow) -> list[CandidateEvent]:
        record = RawSourceRecord(
            source_type=SourceType(doc.source_type),
            jurisdiction=doc.jurisdiction,
            url=doc.url,
            title=doc.title,
            payload=doc.payload or {},
            published_at=doc.published_at,
            retrieved_at=doc.retrieved_at,
            page_locator=doc.page_locator,
            external_id=doc.external_id,
            content_hash=doc.content_hash,
            official_rank=doc.official_rank,
        )
        cands: list[CandidateEvent] = []
        for ex in self._extractors:
            try:
                cands.extend(await ex.extract(source_doc_id=doc.source_doc_id, record=record))
            except Exception:
                log.warning("extractor %s failed for %s", ex.name, doc.source_doc_id, exc_info=True)
        return cands
