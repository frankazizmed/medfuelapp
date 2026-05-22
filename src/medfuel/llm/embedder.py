from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from collections.abc import Sequence

from medfuel.llm.base import LLMUnavailableError


class Embedder(ABC):
    """Returns a fixed-dimension embedding for one or more text chunks."""

    model_id: str = "stub-embed"
    dim: int = 8

    @abstractmethod
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        ...

    async def aclose(self) -> None:  # noqa: B027 (intentional empty default)
        pass


class StubEmbedder(Embedder):
    """Deterministic hash-based pseudo-embedding for tests and offline runs.

    Splits a SHA-256 of the input into eight float dimensions normalised to
    unit length. Not semantically meaningful — but stable, dependency-free,
    and good enough for exercising the chunk/embed/retrieve pipeline end
    to end without any external embedding model.
    """

    model_id = "stub-embed"
    dim = 8

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # 8 dims, each from a 4-byte slice, mapped to [-1, 1].
        raw = [
            int.from_bytes(digest[i * 4 : (i + 1) * 4], "big") / 2**32 - 0.5
            for i in range(self.dim)
        ]
        norm = math.sqrt(sum(v * v for v in raw)) or 1.0
        return [v / norm for v in raw]


class OpenAIEmbedder(Embedder):
    """OpenAI text-embedding-3-small wrapper (lazy import, optional dep)."""

    def __init__(self, *, model: str, api_key: str | None, dim: int = 1536):
        if not api_key:
            raise LLMUnavailableError("OpenAI API key is not configured.")
        try:
            from openai import AsyncOpenAI  # noqa: PLC0415 (intentional lazy import)
        except ImportError as exc:  # pragma: no cover
            raise LLMUnavailableError(
                "openai package not installed. Install with `pip install openai`."
            ) from exc
        self._client = AsyncOpenAI(api_key=api_key)
        self.model_id = model
        self.dim = dim

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:  # pragma: no cover - prod path
        response = await self._client.embeddings.create(
            model=self.model_id, input=list(texts)
        )
        return [d.embedding for d in response.data]

    async def aclose(self) -> None:  # pragma: no cover
        await self._client.close()


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
