from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from medfuel.db.orm import DocumentChunkRow, SourceDocumentRow
from medfuel.extract.chunking import (
    UNSTRUCTURED_SOURCE_TYPES,
    Chunk,
    chunk_text,
    extract_text,
)
from medfuel.llm import Embedder
from medfuel.llm.factory import get_embedder
from medfuel.models import RawSourceRecord, SourceType

log = logging.getLogger(__name__)


class ChunkEmbedPipeline:
    """Chunks unstructured documents, redacts PII/PHI, then embeds the result.

    Restricted to UNSTRUCTURED_SOURCE_TYPES because structured payloads
    already feed the rule extractor — chunking them would burn embedding
    budget without adding signal.
    """

    def __init__(self, embedder: Embedder | None = None):
        self._embedder = embedder or get_embedder()

    @property
    def model_id(self) -> str:
        return self._embedder.model_id

    async def aclose(self) -> None:
        await self._embedder.aclose()

    async def run(self, *, session: Session, company_id: str) -> int:
        """Embed every unstructured document for the company that has no chunks yet.

        Returns the number of chunks newly persisted. Idempotent: existing
        chunks are not re-embedded so reruns are cheap.
        """
        docs = (
            session.query(SourceDocumentRow)
            .filter(
                SourceDocumentRow.company_id == company_id,
                SourceDocumentRow.source_type.in_(
                    [s.value for s in UNSTRUCTURED_SOURCE_TYPES]
                ),
            )
            .all()
        )
        if not docs:
            return 0

        new_chunks = 0
        for doc in docs:
            existing = (
                session.query(DocumentChunkRow)
                .filter(DocumentChunkRow.source_doc_id == doc.source_doc_id)
                .count()
            )
            if existing:
                continue
            record = _row_to_record(doc)
            text = extract_text(record)
            chunks = chunk_text(text)
            if not chunks:
                continue
            embeddings = await self._embedder.embed([c.text for c in chunks])
            for chunk, vector in zip(chunks, embeddings, strict=True):
                session.add(_chunk_to_row(doc, chunk, vector, self._embedder))
                new_chunks += 1
            session.flush()
        return new_chunks


def _row_to_record(row: SourceDocumentRow) -> RawSourceRecord:
    return RawSourceRecord(
        source_type=SourceType(row.source_type),
        jurisdiction=row.jurisdiction,
        url=row.url,
        title=row.title,
        payload=row.payload or {},
        published_at=row.published_at,
        retrieved_at=row.retrieved_at,
        page_locator=row.page_locator,
        external_id=row.external_id,
        content_hash=row.content_hash,
        official_rank=row.official_rank,
    )


def _chunk_to_row(
    doc: SourceDocumentRow,
    chunk: Chunk,
    embedding: list[float],
    embedder: Embedder,
) -> DocumentChunkRow:
    return DocumentChunkRow(
        chunk_id=f"chk_{uuid.uuid4().hex[:12]}",
        source_doc_id=doc.source_doc_id,
        company_id=doc.company_id,
        chunk_index=chunk.chunk_index,
        char_start=chunk.char_start,
        char_end=chunk.char_end,
        chunk_text=chunk.text,
        redaction_count=chunk.redaction_count,
        embedding=embedding,
        embedding_model=embedder.model_id,
        embedding_dim=embedder.dim,
    )
