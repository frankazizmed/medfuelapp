from __future__ import annotations

from medfuel.llm.base import LLMUnavailableError, NarratorLLM


class AnthropicNarrator(NarratorLLM):
    """Claude narrative generator (Opus 4.7 default per design).

    The anthropic SDK is imported lazily; if it or the API key is missing,
    constructing the narrator raises LLMUnavailableError so the orchestrator
    can fall back to the deterministic stub renderer.
    """

    def __init__(self, *, model: str, api_key: str | None):
        if not api_key:
            raise LLMUnavailableError("Anthropic API key is not configured.")
        try:
            from anthropic import AsyncAnthropic  # noqa: PLC0415 (intentional lazy import)
        except ImportError as exc:  # pragma: no cover
            raise LLMUnavailableError(
                "anthropic package not installed. Install with `pip install anthropic`."
            ) from exc
        self._client = AsyncAnthropic(api_key=api_key)
        self.model_id = model

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
        # Concatenate all text blocks into a single string.
        parts: list[str] = []
        for block in message.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts)

    async def aclose(self) -> None:  # pragma: no cover
        await self._client.close()
