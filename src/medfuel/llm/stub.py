from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from medfuel.llm.base import ExtractorLLM, NarratorLLM

T = TypeVar("T", bound=BaseModel)


class StubExtractorLLM(ExtractorLLM):
    """Returns an empty payload of the requested schema.

    Real Phase 2 extraction in CI relies on the rule-based extractor over
    structured payloads. The stub exists so the orchestrator interface stays
    identical whether or not LLM keys are configured — useful for unstructured
    sources (MHRA pages, PMDA narratives, company sites) when running offline.
    """

    model_id = "stub-extractor"

    async def extract(
        self,
        *,
        instructions: str,
        document_text: str,
        schema_model: type[T],
        max_items_hint: int = 25,
    ) -> T:
        # Build a minimal valid instance using model defaults.
        return schema_model.model_construct()


class StubNarratorLLM(NarratorLLM):
    """Deterministic narrative generator used in tests and offline runs.

    Produces a templated institutional summary keyed off the prompt body so
    end-to-end report rendering works without external dependencies. The prompt
    is expected to contain a structured 'sections=' block; we echo it back so
    tests can assert on it deterministically.
    """

    model_id = "stub-narrator"

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.2,
    ) -> str:
        return prompt
