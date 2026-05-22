from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from medfuel.config import get_settings


@dataclass
class RateLimiter:
    """Simple async token-bucket-style limiter.

    `rate_per_second` is the steady-state cap; `burst` allows brief bursts.
    Tracks request budget per limiter instance, so callers should share one
    limiter per upstream host.
    """

    rate_per_second: float
    burst: int = 1
    _tokens: float = 0.0
    _last: float = 0.0
    _lock: asyncio.Lock | None = None

    def __post_init__(self) -> None:
        self._tokens = float(self.burst)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    @classmethod
    def per_minute(cls, rate_per_minute: float, burst: int = 1) -> RateLimiter:
        return cls(rate_per_second=rate_per_minute / 60.0, burst=burst)

    async def acquire(self) -> None:
        assert self._lock is not None
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate_per_second)
            if self._tokens < 1.0:
                wait_s = (1.0 - self._tokens) / max(self.rate_per_second, 1e-6)
                await asyncio.sleep(wait_s)
                self._tokens = 0.0
                self._last = time.monotonic()
            else:
                self._tokens -= 1.0


class RateLimitedClient:
    """Thin httpx.AsyncClient wrapper that applies rate limits and retries.

    Retries 429 and 5xx via tenacity with exponential backoff. Always sends a
    polite User-Agent and identifies the operator email, which the SEC requires
    and NCBI recommends.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        rate_limiter: RateLimiter | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ):
        settings = get_settings()
        merged_headers = {
            "User-Agent": settings.user_agent,
            "From": settings.contact_email,
            "Accept-Encoding": "gzip, deflate",
        }
        if headers:
            merged_headers.update(headers)
        self._client = httpx.AsyncClient(
            base_url=base_url or "",
            headers=merged_headers,
            timeout=timeout or settings.http_timeout_seconds,
        )
        self._limiter = rate_limiter
        self._max_retries = settings.http_max_retries

    async def __aenter__(self) -> RateLimitedClient:
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        retrying = AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=16),
            retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        )
        async for attempt in retrying:
            with attempt:
                if self._limiter is not None:
                    await self._limiter.acquire()
                resp = await self._client.request(
                    method, url, params=params, json=json, headers=headers
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    resp.raise_for_status()
                return resp
        raise RuntimeError("unreachable")

    async def get_json(self, url: str, *, params: dict | None = None) -> dict:
        resp = await self.request("GET", url, params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_text(self, url: str, *, params: dict | None = None) -> str:
        resp = await self.request("GET", url, params=params)
        resp.raise_for_status()
        return resp.text
