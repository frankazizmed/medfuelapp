from __future__ import annotations

from medfuel.llm.base import LLMUnavailableError, NarratorLLM
from medfuel.llm.cost import UsageTracker


class AnthropicNarrator(NarratorLLM):
    """Claude narrative generator (Opus 4.7 default per design).

    The anthropic SDK is imported lazily; if it or the API key is missing,
    constructing the narrator raises LLMUnavailableError so the orchestrator
    can fall back to the deterministic stub renderer.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ):
        if not api_key:
            raise LLMUnavailableError("Anthropic API key is not configured.")
        try:
            from anthropic import AsyncAnthropic  # noqa: PLC0415 (intentional lazy import)
        except ImportError as exc:  # pragma: no cover
            raise LLMUnavailableError(
                "anthropic package not installed. Install with `pip install anthropic`."
            ) from exc
        # The SDK's built-in retry handles 429/5xx/timeouts with exponential
        # backoff (respecting Retry-After), and the timeout caps a single call
        # so a stalled request can't pin the whole generation indefinitely.
        client_kwargs: dict[str, object] = {"api_key": api_key}
        if timeout is not None:
            client_kwargs["timeout"] = timeout
        if max_retries is not None:
            client_kwargs["max_retries"] = max_retries
        self._client = AsyncAnthropic(**client_kwargs)
        self.model_id = model
        # Aggregates this run's token spend so it can be attributed on the report.
        self.usage = UsageTracker()

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.2,
    ) -> str:  # pragma: no cover - exercised against real API in production only
        message = await self._client.messages.create(
            model=self.model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = getattr(message, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        self.usage.record(
            self.model_id, input_tokens=input_tokens, output_tokens=output_tokens
        )
        # Concatenate all text blocks into a single string.
        parts: list[str] = []
        for block in message.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts)

    async def aclose(self) -> None:  # pragma: no cover
        await self._client.close()
