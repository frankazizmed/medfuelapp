from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

log = logging.getLogger("medfuel.trace")


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[dict[str, Any]]:
    """Lightweight span: logs start/end + duration with the bound job context.

    Drop-in compatible with OpenTelemetry's context-manager pattern, so swapping
    this for `opentelemetry.trace.get_tracer().start_as_current_span(...)` later
    is a single-file change. Until an OTEL exporter is configured, recording
    structured timing into our JSON logger is the most useful thing we can do.
    """
    started = time.perf_counter()
    attrs = dict(attributes)
    log.info("span.start", extra={"span": name, **attrs})
    try:
        yield attrs
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        log.info(
            "span.end",
            extra={"span": name, "duration_ms": elapsed_ms, "status": "ok", **attrs},
        )
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        log.warning(
            "span.end",
            extra={
                "span": name,
                "duration_ms": elapsed_ms,
                "status": "error",
                "error": repr(exc),
                **attrs,
            },
        )
        raise
