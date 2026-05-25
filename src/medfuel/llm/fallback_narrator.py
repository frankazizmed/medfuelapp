from __future__ import annotations

import logging

from medfuel.llm.base import LLMUnavailableError, NarratorLLM
from medfuel.llm.cost import UsageTracker

log = logging.getLogger(__name__)


class FallbackNarrator(NarratorLLM):
    """Tries an ordered chain of narrators, degrading instead of discarding work.

    Each section render calls ``generate`` once. If a delegate raises (after its
    own retries), we log and move to the next. With a deterministic stub as the
    terminal delegate, a flaky run still yields a complete report instead of
    billing for partial sections that get thrown away. Token usage from whichever
    delegate produced output is aggregated for cost attribution.
    """

    def __init__(self, delegates: list[NarratorLLM]):
        if not delegates:
            raise ValueError("FallbackNarrator requires at least one delegate")
        self._delegates = delegates
        self.usage = UsageTracker()
        self.section_models: list[str] = []
        self.fallback_sections = 0

    @property
    def model_id(self) -> str:
        return self._delegates[0].model_id

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.2,
    ) -> str:
        last_exc: Exception | None = None
        for index, delegate in enumerate(self._delegates):
            try:
                text = await delegate.generate(
                    system=system,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except Exception as exc:  # noqa: BLE001 — any provider error degrades, never aborts
                last_exc = exc
                log.warning(
                    "narrator delegate %s failed; falling back",
                    delegate.model_id,
                    exc_info=True,
                )
                continue
            last_usage = getattr(delegate, "last_usage", None)
            if last_usage is not None:
                self.usage.record(
                    delegate.model_id,
                    input_tokens=last_usage[0],
                    output_tokens=last_usage[1],
                )
            self.section_models.append(delegate.model_id)
            if index > 0:
                self.fallback_sections += 1
            return text
        raise LLMUnavailableError("All narrator delegates failed") from last_exc

    async def aclose(self) -> None:  # pragma: no cover - exercised in production teardown
        for delegate in self._delegates:
            await delegate.aclose()
