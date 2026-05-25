from __future__ import annotations

from datetime import UTC, datetime

import pytest

from medfuel.adapters.base import SourceAdapter
from medfuel.db.orm import ReportRunRow
from medfuel.db.registry import hash_payload
from medfuel.ingest.pipeline import DiscoveryPipeline, run_discovery
from medfuel.llm.base import NarratorLLM
from medfuel.llm.cost import UsageTracker
from medfuel.models import CompanyIdentity, JurisdictionScope, RawSourceRecord, SourceType
from medfuel.models.schemas import OFFICIAL_RANK


def test_estimate_cost_uses_price_table() -> None:
    usage = UsageTracker()
    usage.record("claude-opus-4-7", input_tokens=1_000_000, output_tokens=1_000_000)
    # 15 (input) + 75 (output) per 1M tokens.
    assert usage.estimate_cost_usd() == pytest.approx(90.0)
    # Unknown models contribute zero rather than guessing.
    usage.record("mystery-model", input_tokens=1_000_000, output_tokens=1_000_000)
    assert usage.estimate_cost_usd() == pytest.approx(90.0)


def test_usage_aggregates_across_calls() -> None:
    usage = UsageTracker()
    usage.record("claude-opus-4-7", input_tokens=100, output_tokens=200)
    usage.record("claude-opus-4-7", input_tokens=100, output_tokens=200)
    assert usage.input_tokens == 200
    assert usage.output_tokens == 400
    assert usage.by_model["claude-opus-4-7"].calls == 2


class _UsageNarrator(NarratorLLM):
    """Stand-in for AnthropicNarrator that records fixed usage per call."""

    model_id = "claude-opus-4-7"

    def __init__(self) -> None:
        self.usage = UsageTracker()

    async def generate(self, *, system, prompt, max_tokens=1500, temperature=0.2) -> str:
        self.usage.record(self.model_id, input_tokens=10, output_tokens=20)
        return "section body"


def _record(source: SourceType, url: str, payload: dict) -> RawSourceRecord:
    return RawSourceRecord(
        source_type=source,
        jurisdiction="US",
        url=url,
        title="t",
        payload=payload,
        retrieved_at=datetime.now(UTC),
        content_hash=hash_payload(url, payload, title="t"),
        official_rank=OFFICIAL_RANK[source],
    )


class _FDAStub(SourceAdapter):
    source_type = SourceType.FDA
    jurisdiction = "US"

    def __init__(self, records: list[RawSourceRecord]) -> None:
        self._records = records

    async def discover(self, identity, scope):
        return list(self._records)


@pytest.mark.asyncio
async def test_report_persists_narrative_usage(db_session, monkeypatch) -> None:
    from medfuel.render import report as report_module

    fake = _UsageNarrator()
    monkeypatch.setattr(report_module, "get_narrator_llm", lambda: fake)

    records = [
        _record(
            SourceType.FDA,
            "https://api.fda.gov/device/510k.json?stub=1",
            {
                "k_number": "K991234",
                "device_name": "Examplon Stent",
                "decision_date": "20240115",
                "decision_description": "Substantially Equivalent",
            },
        ),
    ]
    pipeline = DiscoveryPipeline(adapters=[_FDAStub(records)])
    result = await run_discovery(
        identity=CompanyIdentity(name="Example Tx"),
        scope=JurisdictionScope(sources=[SourceType.FDA]),
        pipeline=pipeline,
        session=db_session,
    )

    report = db_session.get(ReportRunRow, result.report_id)
    meta = report.layout_plan["narrative_generation"]
    calls = meta["by_model"]["claude-opus-4-7"]["calls"]
    assert calls >= 1
    assert meta["model"] == "claude-opus-4-7"
    assert meta["input_tokens"] == calls * 10
    assert meta["output_tokens"] == calls * 20
    assert meta["estimated_cost_usd"] > 0
