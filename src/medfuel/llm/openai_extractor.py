from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from medfuel.llm.base import ExtractorLLM, LLMUnavailableError

T = TypeVar("T", bound=BaseModel)


class OpenAIExtractor(ExtractorLLM):
    """OpenAI Responses + Structured Outputs implementation.

    The openai SDK is imported lazily; if it or the API key is missing,
    constructing the extractor raises LLMUnavailableError so callers can
    fall back to the stub.
    """

    def __init__(self, *, model: str, api_key: str | None):
        if not api_key:
            raise LLMUnavailableError("OpenAI API key is not configured.")
        try:
            from openai import AsyncOpenAI  # noqa: PLC0415 (intentional lazy import)
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise LLMUnavailableError(
                "openai package not installed. Install with `pip install openai`."
            ) from exc
        self._client = AsyncOpenAI(api_key=api_key)
        self.model_id = model

    async def extract(
        self,
        *,
        instructions: str,
        document_text: str,
        schema_model: type[T],
        max_items_hint: int = 25,
    ) -> T:  # pragma: no cover - exercised against real API in production only
        response = await self._client.responses.parse(
            model=self.model_id,
            input=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": document_text[:120_000]},
            ],
            text_format=schema_model,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise RuntimeError("OpenAI returned no parsed output for structured request.")
        return parsed

    async def aclose(self) -> None:  # pragma: no cover
        await self._client.close()
