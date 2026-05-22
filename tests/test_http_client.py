from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import respx

from medfuel.http.client import RateLimitedClient, RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_paces_calls():
    limiter = RateLimiter(rate_per_second=10.0, burst=1)
    start = time.monotonic()
    for _ in range(3):
        await limiter.acquire()
    elapsed = time.monotonic() - start
    # 3 calls at 10/sec with burst=1 should take at least ~0.18s.
    assert elapsed >= 0.18


@pytest.mark.asyncio
@respx.mock
async def test_client_sends_user_agent_and_from_header():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"ok": True})

    respx.get("https://api.example.com/x").mock(side_effect=handler)

    client = RateLimitedClient(base_url="https://api.example.com")
    try:
        data = await client.get_json("/x")
    finally:
        await client.aclose()
    assert data == {"ok": True}
    assert "user-agent" in captured["headers"]
    assert "from" in captured["headers"]


@pytest.mark.asyncio
@respx.mock
async def test_client_retries_on_5xx_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    respx.get("https://api.example.com/retry").mock(side_effect=handler)

    # Skip tenacity backoff sleeps to keep the test fast.
    async def fast_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    client = RateLimitedClient(base_url="https://api.example.com")
    try:
        data = await client.get_json("/retry")
    finally:
        await client.aclose()
    assert data == {"ok": True}
    assert calls["n"] == 2
