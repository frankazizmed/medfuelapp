from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMUnavailableError(RuntimeError):
    """Raised when a requested LLM provider is configured but its SDK or key is missing."""


class ExtractorLLM(ABC):
    """Schema-constrained extraction. Mirrors the OpenAI Structured Outputs contract."""

    model_id: str = "stub"

    @abstractmethod
    async def extract(
        self,
        *,
        instructions: str,
        document_text: str,
        schema_model: type[T],
        max_items_hint: int = 25,
    ) -> T:
        """Return a Pydantic instance validated against the supplied schema model."""

    async def aclose(self) -> None:  # noqa: B027 (intentional empty default)
        pass


class NarratorLLM(ABC):
    """Free-text generation for the institutional narrative renderer."""

    model_id: str = "stub"

    @abstractmethod
    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.2,
    ) -> str:
        ...

    async def aclose(self) -> None:  # noqa: B027
        pass
