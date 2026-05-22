from __future__ import annotations

import logging
from datetime import date

from pydantic import BaseModel, Field

from medfuel.db.orm import DocumentChunkRow
from medfuel.extract.base import Extractor
from medfuel.extract.chunking import UNSTRUCTURED_SOURCE_TYPES, chunk_text, extract_text
from medfuel.extract.normalize import normalize_agency, normalize_date
from medfuel.llm.base import ExtractorLLM
from medfuel.llm.factory import get_extractor_llm
from medfuel.models import CandidateEvent, RawSourceRecord

log = logging.getLogger(__name__)


_INSTRUCTIONS = (
    "Extract regulatory events from the supplied document text. Only emit "
    "events that are explicitly stated; do not infer dates or agencies. If "
    "no event is present return an empty list."
)


class _LLMCandidate(BaseModel):
    """Schema fed to OpenAI Structured Outputs. Mirrors CandidateEvent but
    allows the model to return strings the extractor will normalize."""

    agency: str
    jurisdiction: str
    event_type: str
    status: str
    summary: str
    event_date: str | None = None
    asset_name: str | None = None
    investor_importance: int = Field(default=3, ge=1, le=5)
    evidence_strength: int = Field(default=3, ge=1, le=5)
    source_excerpt: str | None = None


class _LLMExtraction(BaseModel):
    candidates: list[_LLMCandidate] = Field(default_factory=list)


_ALLOWED_EVENT_TYPES = {
    "approval",
    "clearance",
    "designation",
    "clinical_hold",
    "warning",
    "inspection",
    "label_change",
    "trial_update",
    "patent_event",
    "offering_or_filing",
    "manufacturing_issue",
}


class LLMExtractor(Extractor):
    """Extracts events from unstructured documents via OpenAI Structured Outputs.

    Consumes any DocumentChunkRow rows already persisted for the document.
    If chunks are missing (because chunking hasn't run yet), falls back to
    chunking the document inline. Always degrades safely: the StubExtractorLLM
    returns no candidates so the pipeline still completes.
    """

    name = "llm"

    def __init__(self, llm: ExtractorLLM | None = None):
        self._llm = llm or get_extractor_llm()

    @property
    def model_id(self) -> str:
        return self._llm.model_id

    async def aclose(self) -> None:
        await self._llm.aclose()

    async def extract(
        self,
        *,
        source_doc_id: str,
        record: RawSourceRecord,
    ) -> list[CandidateEvent]:
        if record.source_type not in UNSTRUCTURED_SOURCE_TYPES:
            return []
        text = extract_text(record)
        if not text:
            return []
        # Fan out to one chunk's worth of context; we limit to the first six
        # chunks to keep model token usage predictable for unstructured pages.
        chunks = chunk_text(text)[:6]
        if not chunks:
            return []
        document_text = "\n\n".join(c.text for c in chunks)
        try:
            result = await self._llm.extract(
                instructions=_INSTRUCTIONS,
                document_text=document_text,
                schema_model=_LLMExtraction,
            )
        except Exception:
            log.warning(
                "LLM extraction failed for %s", source_doc_id, exc_info=True
            )
            return []
        return self._convert(result, source_doc_id=source_doc_id, jurisdiction=record.jurisdiction)

    @staticmethod
    async def from_persisted_chunks(
        *,
        chunks: list[DocumentChunkRow],
        source_doc_id: str,
        jurisdiction: str,
        llm: ExtractorLLM,
    ) -> list[CandidateEvent]:
        """Variant entry point used when chunks are already in the database."""
        if not chunks:
            return []
        document_text = "\n\n".join(c.chunk_text for c in chunks[:6])
        try:
            result = await llm.extract(
                instructions=_INSTRUCTIONS,
                document_text=document_text,
                schema_model=_LLMExtraction,
            )
        except Exception:
            log.warning("LLM extraction failed for %s", source_doc_id, exc_info=True)
            return []
        return LLMExtractor._convert(
            result, source_doc_id=source_doc_id, jurisdiction=jurisdiction
        )

    @staticmethod
    def _convert(
        result: _LLMExtraction, *, source_doc_id: str, jurisdiction: str
    ) -> list[CandidateEvent]:
        out: list[CandidateEvent] = []
        for raw in result.candidates:
            event_type = raw.event_type.strip().lower()
            if event_type not in _ALLOWED_EVENT_TYPES:
                continue
            event_date: date | None = normalize_date(raw.event_date)
            out.append(
                CandidateEvent(
                    agency=normalize_agency(raw.agency),
                    jurisdiction=raw.jurisdiction or jurisdiction,
                    event_type=event_type,  # type: ignore[arg-type]
                    status=raw.status or "reported",
                    summary=raw.summary,
                    event_date=event_date,
                    asset_name=raw.asset_name,
                    investor_importance=raw.investor_importance,
                    evidence_strength=min(raw.evidence_strength, 3),
                    source_doc_id=source_doc_id,
                    source_excerpt=raw.source_excerpt,
                    extractor="llm",
                )
            )
        return out
