from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from medfuel.extract.llm_extractor import (
    LLMExtractor,
    _LLMCandidate,
    _LLMExtraction,
)
from medfuel.llm.base import ExtractorLLM
from medfuel.models import RawSourceRecord, SourceType
from medfuel.models.schemas import OFFICIAL_RANK


class _FakeLLM(ExtractorLLM):
    model_id = "fake-extract"

    def __init__(self, payload: _LLMExtraction):
        self._payload = payload

    async def extract(self, *, instructions, document_text, schema_model, max_items_hint=25):
        assert issubclass(schema_model, BaseModel)
        return self._payload


def _record(text: str, source: SourceType = SourceType.COMPANY) -> RawSourceRecord:
    return RawSourceRecord(
        source_type=source,
        jurisdiction="GLOBAL",
        url="https://example.com/news",
        title="news",
        payload={"markdown": text},
        retrieved_at=datetime.now(UTC),
        content_hash="h",
        official_rank=OFFICIAL_RANK[source],
    )


@pytest.mark.asyncio
async def test_llm_extractor_skips_structured_sources():
    extractor = LLMExtractor(llm=_FakeLLM(_LLMExtraction()))
    rec = _record("FDA approved Acmenil.", source=SourceType.FDA)
    result = await extractor.extract(source_doc_id="src_1", record=rec)
    assert result == []


@pytest.mark.asyncio
async def test_llm_extractor_normalizes_and_filters_event_types():
    payload = _LLMExtraction(
        candidates=[
            _LLMCandidate(
                agency="u.s. food and drug administration",
                jurisdiction="US",
                event_type="approval",
                status="AP",
                summary="FDA approved Acmenil on Jan 15 2025.",
                event_date="2025-01-15",
                asset_name="Acmenil",
                investor_importance=5,
                evidence_strength=4,
            ),
            _LLMCandidate(
                agency="FDA",
                jurisdiction="US",
                event_type="not_a_real_event_type",
                status="?",
                summary="should be dropped",
            ),
        ]
    )
    extractor = LLMExtractor(llm=_FakeLLM(payload))
    rec = _record("FDA approved Acmenil on Jan 15 2025.")
    candidates = await extractor.extract(source_doc_id="src_1", record=rec)
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.agency == "FDA"
    assert cand.event_type == "approval"
    assert cand.event_date.isoformat() == "2025-01-15"
    # LLM-derived evidence_strength is capped at 3 (regulator records still
    # outrank model output).
    assert cand.evidence_strength <= 3
    assert cand.extractor == "llm"


@pytest.mark.asyncio
async def test_llm_extractor_returns_empty_on_no_text():
    extractor = LLMExtractor(llm=_FakeLLM(_LLMExtraction()))
    rec = RawSourceRecord(
        source_type=SourceType.COMPANY,
        jurisdiction="GLOBAL",
        url="https://example.com/empty",
        title="empty",
        payload={},
        retrieved_at=datetime.now(UTC),
        content_hash="h",
        official_rank=OFFICIAL_RANK[SourceType.COMPANY],
    )
    assert await extractor.extract(source_doc_id="src_1", record=rec) == []
