from __future__ import annotations

from datetime import UTC, datetime

import pytest

from medfuel.adapters.base import SourceAdapter
from medfuel.db.orm import ReportRunRow
from medfuel.db.registry import hash_payload
from medfuel.ingest.pipeline import DiscoveryPipeline, run_discovery
from medfuel.llm.base import NarratorLLM
from medfuel.llm.cost import UsageTracker
from medfuel.llm.fallback_narrator import FallbackNarrator
from medfuel.llm.stub import StubNarratorLLM
from medfuel.models import CompanyIdentity, JurisdictionScope, RawSourceRecord, SourceType
from medfuel.models.schemas import OFFICIAL_RANK


class _FailingNarrator(NarratorLLM):
    model_id = "fail-model"

    def __init__(self) -> None:
        self.last_usage: tuple[int, int] | None = None

    async def generate(self, *, system, prompt, max_tokens=1500, temperature=0.2) -> str:
        raise RuntimeError("boom")


class _OkNarrator(NarratorLLM):
    def __init__(self, model_id: str, text: str, usage: tuple[int, int]) -> None:
        self.model_id = model_id
        self._text = text
        self.last_usage = usage

    async def generate(self, *, system, prompt, max_tokens=1500, temperature=0.2) -> str:
        return self._text


def test_estimate_cost_uses_price_table() -> None:
    usage = UsageTracker()
    usage.record("claude-opus-4-7", input_tokens=1_000_000, output_tokens=1_000_000)
    # 15 (input) + 75 (output) per 1M tokens.
    assert usage.estimate_cost_usd() == pytest.approx(90.0)
    # Unknown models contribute zero rather than guessing.
    usage.record("mystery-model", input_tokens=1_000_000, output_tokens=1_000_000)
    assert usage.estimate_cost_usd() == pytest.approx(90.0)


@pytest.mark.asyncio
async def test_fallback_uses_secondary_when_primary_fails() -> None:
    narrator = FallbackNarrator(
        [
            _FailingNarrator(),
            _OkNarrator("claude-sonnet-4-6", "sonnet text", (5, 7)),
            StubNarratorLLM(),
        ]
    )
    out = await narrator.generate(system="s", prompt="p")
    assert out == "sonnet text"
    assert narrator.fallback_sections == 1
    assert narrator.usage.output_tokens == 7
    assert narrator.usage.by_model["claude-sonnet-4-6"].calls == 1


@pytest.mark.asyncio
async def test_fallback_to_stub_when_all_models_fail() -> None:
    prompt = "sections=executive_summary\nobjective=x"
    narrator = FallbackNarrator([_FailingNarrator(), _FailingNarrator(), StubNarratorLLM()])
    out = await narrator.generate(system="s", prompt=prompt)
    # Stub echoes the prompt, so render() still completes and the report commits.
    assert out == prompt
    assert narrator.fallback_sections == 1
    # The stub reports no usage, so no spend is attributed.
    assert narrator.usage.input_tokens == 0
    assert narrator.usage.estimate_cost_usd() == 0.0


@pytest.mark.asyncio
async def test_usage_aggregates_across_calls() -> None:
    narrator = FallbackNarrator(
        [_OkNarrator("claude-opus-4-7", "x", (100, 200)), StubNarratorLLM()]
    )
    await narrator.generate(system="s", prompt="p")
    await narrator.generate(system="s", prompt="p")
    assert narrator.usage.input_tokens == 200
    assert narrator.usage.output_tokens == 400
    assert narrator.usage.by_model["claude-opus-4-7"].calls == 2
    assert narrator.fallback_sections == 0
    assert narrator.usage.estimate_cost_usd() > 0


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

    fake = FallbackNarrator(
        [_OkNarrator("claude-opus-4-7", "section body", (10, 20)), StubNarratorLLM()]
    )
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
    assert meta["primary_model"] == "claude-opus-4-7"
    assert meta["degraded"] is False
    assert meta["input_tokens"] == calls * 10
    assert meta["output_tokens"] == calls * 20
    assert meta["estimated_cost_usd"] > 0
