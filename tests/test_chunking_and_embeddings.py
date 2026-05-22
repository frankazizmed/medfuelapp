from __future__ import annotations

from datetime import UTC, datetime

import pytest

from medfuel.db.orm import CompanyRow, DocumentChunkRow, SourceDocumentRow
from medfuel.db.registry import hash_payload
from medfuel.extract.chunking import (
    UNSTRUCTURED_SOURCE_TYPES,
    chunk_text,
    extract_text,
)
from medfuel.extract.embeddings import ChunkEmbedPipeline
from medfuel.llm import StubEmbedder, cosine_similarity
from medfuel.models import RawSourceRecord, SourceType
from medfuel.models.schemas import OFFICIAL_RANK
from medfuel.verify import find_similar_chunks


def test_chunk_text_respects_size_and_overlap():
    text = "a" * 2500
    chunks = chunk_text(text, chunk_size=800, overlap=100)
    # 2500 chars with stride 700 -> 4 chunks (0-800, 700-1500, 1400-2200, 2100-2500)
    assert len(chunks) == 4
    assert chunks[0].char_start == 0 and chunks[0].char_end == 800
    assert chunks[1].char_start == 700 and chunks[1].char_end == 1500
    assert chunks[-1].char_end == 2500


def test_extract_text_prefers_markdown_field():
    record = RawSourceRecord(
        source_type=SourceType.COMPANY,
        jurisdiction="GLOBAL",
        url="https://example.com",
        title="Pipeline",
        payload={"markdown": "# Pipeline\nPhase 3 ongoing.", "extra": "ignored"},
        retrieved_at=datetime.now(UTC),
        content_hash="h",
        official_rank=OFFICIAL_RANK[SourceType.COMPANY],
    )
    assert "Phase 3 ongoing" in extract_text(record)


def test_unstructured_source_types_covers_expected_set():
    assert SourceType.MHRA in UNSTRUCTURED_SOURCE_TYPES
    assert SourceType.PMDA in UNSTRUCTURED_SOURCE_TYPES
    assert SourceType.COMPANY in UNSTRUCTURED_SOURCE_TYPES
    assert SourceType.FDA not in UNSTRUCTURED_SOURCE_TYPES  # structured
    assert SourceType.SEC not in UNSTRUCTURED_SOURCE_TYPES  # structured


def _seed_company_with_company_doc(session, *, text: str = "FDA approved Acmenil on Jan 15 2025.") -> tuple[str, str]:
    company = CompanyRow(company_id="cmp_emb", legal_name="EmbedCo")
    session.add(company)
    url = "https://example.com/news"
    payload = {"markdown": text, "metadata": {"sourceURL": url}}
    doc = SourceDocumentRow(
        source_doc_id="src_emb_1",
        company_id="cmp_emb",
        job_id=None,
        source_type=SourceType.COMPANY.value,
        jurisdiction="GLOBAL",
        url=url,
        title="Pipeline update",
        payload=payload,
        published_at=None,
        retrieved_at=datetime.now(UTC),
        page_locator=None,
        external_id=None,
        content_hash=hash_payload(url, payload, title="Pipeline update"),
        official_rank=OFFICIAL_RANK[SourceType.COMPANY],
    )
    session.add(doc)
    session.commit()
    return "cmp_emb", "src_emb_1"


@pytest.mark.asyncio
async def test_chunk_embed_pipeline_persists_chunks_with_stub_embedder(db_session):
    company_id, source_doc_id = _seed_company_with_company_doc(
        db_session, text="Acmenil received FDA approval on January 15 2025."
    )
    pipeline = ChunkEmbedPipeline(embedder=StubEmbedder())
    n = await pipeline.run(session=db_session, company_id=company_id)
    db_session.commit()
    assert n >= 1

    chunks = db_session.query(DocumentChunkRow).all()
    assert len(chunks) == n
    assert chunks[0].source_doc_id == source_doc_id
    assert chunks[0].embedding is not None
    assert len(chunks[0].embedding) == StubEmbedder().dim
    assert chunks[0].embedding_model == "stub-embed"


@pytest.mark.asyncio
async def test_chunk_embed_pipeline_is_idempotent(db_session):
    company_id, _ = _seed_company_with_company_doc(db_session)
    pipeline = ChunkEmbedPipeline(embedder=StubEmbedder())
    first = await pipeline.run(session=db_session, company_id=company_id)
    db_session.commit()
    second = await pipeline.run(session=db_session, company_id=company_id)
    db_session.commit()
    assert first >= 1
    assert second == 0  # already embedded


@pytest.mark.asyncio
async def test_find_similar_chunks_returns_top_match(db_session):
    company_id, source_doc_id = _seed_company_with_company_doc(
        db_session, text="Acmenil received FDA approval on January 15 2025."
    )
    embedder = StubEmbedder()
    pipeline = ChunkEmbedPipeline(embedder=embedder)
    await pipeline.run(session=db_session, company_id=company_id)
    db_session.commit()

    # Querying with the exact chunk text should return the chunk itself at the top.
    chunk_row = db_session.query(DocumentChunkRow).first()
    matches = await find_similar_chunks(
        session=db_session,
        company_id=company_id,
        query_text=chunk_row.chunk_text,
        embedder=embedder,
        top_k=3,
        min_score=0.0,
    )
    assert matches
    assert matches[0].chunk_id == chunk_row.chunk_id
    assert matches[0].score == pytest.approx(1.0, abs=1e-6)


def test_cosine_similarity_handles_edge_cases():
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
