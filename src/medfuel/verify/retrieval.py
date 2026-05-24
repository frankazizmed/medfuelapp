from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from medfuel.db.orm import DocumentChunkRow
from medfuel.llm import Embedder, cosine_similarity


@dataclass
class ChunkMatch:
    chunk_id: str
    source_doc_id: str
    score: float
    text: str
    char_start: int
    char_end: int


async def find_similar_chunks(
    *,
    session: Session,
    company_id: str,
    query_text: str,
    embedder: Embedder,
    top_k: int = 5,
    min_score: float = 0.55,
) -> list[ChunkMatch]:
    """Return the top-k chunks for a query, ranked by cosine similarity.

    Uses exact in-memory similarity over a per-company candidate set —
    appropriate for SQLite. Swap the loop for a pgvector `<=>` query when
    you migrate to Postgres; the score thresholds and return shape are
    deliberately the same so the verifier stays untouched.
    """
    [query_vec] = await embedder.embed([query_text])
    chunks = (
        session.query(DocumentChunkRow)
        .filter(DocumentChunkRow.company_id == company_id)
        .filter(DocumentChunkRow.embedding.is_not(None))
        .all()
    )
    scored: list[ChunkMatch] = []
    for chunk in chunks:
        if not chunk.embedding:
            continue
        score = cosine_similarity(query_vec, chunk.embedding)
        if score < min_score:
            continue
        scored.append(
            ChunkMatch(
                chunk_id=chunk.chunk_id,
                source_doc_id=chunk.source_doc_id,
                score=score,
                text=chunk.chunk_text,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
            )
        )
    scored.sort(key=lambda m: m.score, reverse=True)
    return scored[:top_k]
