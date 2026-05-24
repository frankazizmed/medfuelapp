from __future__ import annotations

import json
import logging

import pytest

from medfuel.observability import (
    bind_job_context,
    clear_job_context,
    configure_logging,
    get_job_context,
    span,
)


def test_job_context_round_trips_per_task():
    clear_job_context()
    assert get_job_context() == {}
    bind_job_context(job_id="job_x", company_id="cmp_y")
    bind_job_context(extra="z")
    ctx = get_job_context()
    assert ctx == {"job_id": "job_x", "company_id": "cmp_y", "extra": "z"}
    clear_job_context()
    assert get_job_context() == {}


def test_json_formatter_includes_bound_context(capsys):
    clear_job_context()
    configure_logging("INFO")
    bind_job_context(job_id="job_123")
    logging.getLogger("medfuel.test").info("hello", extra={"thing": 42})
    captured = capsys.readouterr().out.strip().splitlines()
    assert captured, "expected JSON log lines on stdout"
    record = json.loads(captured[-1])
    assert record["message"] == "hello"
    assert record["job_id"] == "job_123"
    assert record["thing"] == 42
    assert record["level"] == "INFO"
    clear_job_context()


@pytest.mark.asyncio
async def test_span_logs_ok_and_duration(capsys):
    configure_logging("INFO")
    with span("test.span", item_count=3):
        pass
    out = capsys.readouterr().out.strip().splitlines()
    end_records = [json.loads(line) for line in out if "span.end" in line]
    assert end_records
    end = end_records[-1]
    assert end["status"] == "ok"
    assert "duration_ms" in end
    assert end["item_count"] == 3


def test_span_logs_error_and_rethrows(capsys):
    configure_logging("INFO")
    with pytest.raises(ValueError), span("test.fail"):
        raise ValueError("boom")
    out = capsys.readouterr().out.strip().splitlines()
    end_records = [json.loads(line) for line in out if "span.end" in line]
    assert end_records and end_records[-1]["status"] == "error"
