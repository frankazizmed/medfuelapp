from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# USD per 1M tokens as (input, output). Approximate list prices; a model that
# isn't listed contributes zero cost rather than guessing.
_PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
}


@dataclass
class _ModelUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0


@dataclass
class UsageTracker:
    """Accumulates token usage per model so a run's Anthropic spend is attributable."""

    by_model: dict[str, _ModelUsage] = field(default_factory=dict)

    def record(self, model: str, *, input_tokens: int, output_tokens: int) -> None:
        usage = self.by_model.setdefault(model, _ModelUsage())
        usage.input_tokens += input_tokens
        usage.output_tokens += output_tokens
        usage.calls += 1

    @property
    def input_tokens(self) -> int:
        return sum(u.input_tokens for u in self.by_model.values())

    @property
    def output_tokens(self) -> int:
        return sum(u.output_tokens for u in self.by_model.values())

    def estimate_cost_usd(self) -> float:
        total = 0.0
        for model, usage in self.by_model.items():
            in_price, out_price = _PRICES_PER_MTOK.get(model, (0.0, 0.0))
            total += usage.input_tokens / 1_000_000 * in_price
            total += usage.output_tokens / 1_000_000 * out_price
        return round(total, 4)

    def summary(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": self.estimate_cost_usd(),
            "by_model": {
                model: {
                    "input_tokens": u.input_tokens,
                    "output_tokens": u.output_tokens,
                    "calls": u.calls,
                }
                for model, u in self.by_model.items()
            },
        }
