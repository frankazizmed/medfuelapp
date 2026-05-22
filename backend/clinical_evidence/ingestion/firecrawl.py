"""Firecrawl wrapper for retrieving and cleaning HTML pages."""

from __future__ import annotations

import logging

from clinical_evidence.config import get_settings
from clinical_evidence.discovery._http import fetch_json

log = logging.getLogger(__name__)

_FIRECRAWL = "https://api.firecrawl.dev/v1/scrape"


async def scrape(url: str) -> str | None:
    settings = get_settings()
    if not settings.firecrawl_api_key:
        return None
    try:
        data = await fetch_json(
            _FIRECRAWL,
            method="POST",
            headers={
                "Authorization": f"Bearer {settings.firecrawl_api_key}",
                "Content-Type": "application/json",
            },
            json_body={"url": url, "formats": ["markdown"]},
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Firecrawl scrape failed for %s: %s", url, exc)
        return None
    return ((data or {}).get("data", {}) or {}).get("markdown")
