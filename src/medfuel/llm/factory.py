from __future__ import annotations

import logging

from medfuel.config import get_settings
from medfuel.llm.base import ExtractorLLM, LLMUnavailableError, NarratorLLM
from medfuel.llm.embedder import Embedder, StubEmbedder
from medfuel.llm.stub import StubExtractorLLM, StubNarratorLLM

log = logging.getLogger(__name__)


def get_extractor_llm() -> ExtractorLLM:
    """Return an extractor implementation per settings, falling back to the stub.

    Wiring `MEDFUEL_USE_LLM=1` plus `MEDFUEL_OPENAI_API_KEY=...` enables the
    real OpenAI client. Otherwise the stub is returned, which keeps the rest
    of the pipeline functional without external dependencies.
    """
    settings = get_settings()
    if not settings.use_llm:
        return StubExtractorLLM()
    try:
        from medfuel.llm.openai_extractor import OpenAIExtractor  # noqa: PLC0415

        return OpenAIExtractor(
            model=settings.extraction_model, api_key=settings.openai_api_key
        )
    except LLMUnavailableError as exc:
        log.warning("OpenAI extractor unavailable, falling back to stub: %s", exc)
        return StubExtractorLLM()


def get_narrator_llm() -> NarratorLLM:
    """Return a narrator implementation per settings, falling back to the stub."""
    settings = get_settings()
    if not settings.use_llm:
        return StubNarratorLLM()
    try:
        from medfuel.llm.anthropic_narrator import AnthropicNarrator  # noqa: PLC0415

        return AnthropicNarrator(
            model=settings.narrative_model, api_key=settings.anthropic_api_key
        )
    except LLMUnavailableError as exc:
        log.warning("Anthropic narrator unavailable, falling back to stub: %s", exc)
        return StubNarratorLLM()


def get_embedder() -> Embedder:
    """Return an embedder per settings, falling back to the stub."""
    settings = get_settings()
    if not settings.use_llm:
        return StubEmbedder()
    try:
        from medfuel.llm.embedder import OpenAIEmbedder  # noqa: PLC0415

        return OpenAIEmbedder(model=settings.embedding_model, api_key=settings.openai_api_key)
    except LLMUnavailableError as exc:
        log.warning("OpenAI embedder unavailable, falling back to stub: %s", exc)
        return StubEmbedder()
