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
    """Return the narrator per settings, falling back to the stub only when off.

    With LLM routing on we use the configured Opus model and nothing lesser: a
    transient failure is retried (by the SDK) on the SAME model, but a genuine
    failure surfaces as a failed job rather than silently shipping a lower-quality
    Sonnet or templated report. Quality is never downgraded behind the user's back.
    The deterministic stub is only used when LLM routing is disabled entirely
    (CI / offline), which is an explicit choice, not a degraded run.
    """
    settings = get_settings()
    if not settings.use_llm:
        return StubNarratorLLM()
    try:
        from medfuel.llm.anthropic_narrator import AnthropicNarrator  # noqa: PLC0415

        return AnthropicNarrator(
            model=settings.narrative_model,
            api_key=settings.anthropic_api_key,
            timeout=settings.anthropic_timeout_seconds,
            max_retries=settings.anthropic_max_retries,
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
