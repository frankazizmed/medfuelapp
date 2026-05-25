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
    """Return a narrator implementation per settings, falling back to the stub.

    With LLM routing on, the narrator is a FallbackNarrator chaining the primary
    Opus model → the cheaper Sonnet model → the deterministic stub, so a flaky
    Anthropic call degrades to a still-complete report rather than discarding the
    sections already paid for.
    """
    settings = get_settings()
    if not settings.use_llm:
        return StubNarratorLLM()
    try:
        from medfuel.llm.anthropic_narrator import AnthropicNarrator  # noqa: PLC0415
        from medfuel.llm.fallback_narrator import FallbackNarrator  # noqa: PLC0415

        def _build(model: str) -> AnthropicNarrator:
            return AnthropicNarrator(
                model=model,
                api_key=settings.anthropic_api_key,
                timeout=settings.anthropic_timeout_seconds,
                max_retries=settings.anthropic_max_retries,
            )

        delegates: list[NarratorLLM] = [_build(settings.narrative_model)]
        fallback_model = settings.narrative_fallback_model
        if fallback_model and fallback_model != settings.narrative_model:
            delegates.append(_build(fallback_model))
        delegates.append(StubNarratorLLM())
        return FallbackNarrator(delegates)
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
