"""Thin Anthropic SDK wrapper with prompt caching for the system block."""

from __future__ import annotations

import json
import logging
from typing import Any

from clinical_evidence.config import get_settings

log = logging.getLogger(__name__)


def _client():
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic  # type: ignore
    except ImportError:  # pragma: no cover
        log.warning("anthropic SDK not installed; narrative will use fallback.")
        return None
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def generate_page_blocks(
    *,
    system_prompt: str,
    page_instructions: str,
    brief_json: dict[str, Any],
    block_schema: dict[str, Any],
) -> list[dict] | None:
    """Call Claude with a cached system prompt. Returns a list of page blocks.

    The system prompt is sent with cache_control so subsequent page calls reuse it.
    Returns None on failure so the caller can fall back to the deterministic composer.
    """

    settings = get_settings()
    client = _client()
    if client is None:
        return None

    try:
        response = client.messages.create(
            model=settings.narrative_model,
            max_tokens=1500,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Page instructions:\n{page_instructions}\n\n"
                        f"Brief:\n{json.dumps(brief_json, indent=2)}\n\n"
                        f"Return ONLY a JSON array of page blocks conforming to this schema:\n"
                        f"{json.dumps(block_schema, indent=2)}"
                    ),
                }
            ],
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Anthropic narrative call failed: %s", exc)
        return None

    raw = "".join(part.text for part in response.content if getattr(part, "type", None) == "text")
    raw = raw.strip()
    # Tolerate fenced code blocks
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()

    try:
        blocks = json.loads(raw)
        if not isinstance(blocks, list):
            raise ValueError("expected JSON array")
        return blocks
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to parse Claude narrative JSON: %s", exc)
        return None
