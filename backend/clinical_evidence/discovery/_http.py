"""Shared HTTP helpers for discovery fetchers."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

import httpx

from clinical_evidence.config import get_settings

log = logging.getLogger(__name__)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def fetch_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    json_body: dict | None = None,
    retries: int = 3,
) -> dict | list:
    settings = get_settings()
    h = {"Accept": "application/json", **(headers or {})}
    backoff = 1.0
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
        for attempt in range(retries):
            try:
                resp = await client.request(method, url, params=params, headers=h, json=json_body)
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = exc
                log.warning("fetch_json failed (%s) attempt %s: %s", url, attempt + 1, exc)
                await asyncio.sleep(backoff)
                backoff *= 2
    raise RuntimeError(f"fetch_json exhausted retries for {url}: {last_exc}")


async def fetch_text(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    retries: int = 3,
) -> str:
    settings = get_settings()
    h = {"Accept": "*/*", **(headers or {})}
    backoff = 1.0
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
        for attempt in range(retries):
            try:
                resp = await client.get(url, params=params, headers=h)
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPError as exc:
                last_exc = exc
                log.warning("fetch_text failed (%s) attempt %s: %s", url, attempt + 1, exc)
                await asyncio.sleep(backoff)
                backoff *= 2
    raise RuntimeError(f"fetch_text exhausted retries for {url}: {last_exc}")
