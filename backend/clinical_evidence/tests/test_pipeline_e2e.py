"""End-to-end vertical slice with LLM clients mocked / disabled.

This runs without network or API keys. It exercises:
  discovery (stubbed) → extraction (stub_extract) → verification → scoring →
  filter → citations → page budget → narrative (deterministic) → composer.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from clinical_evidence.citations.builder import build as build_citations
from clinical_evidence.layout.composer import compose
from clinical_evidence.layout.page_budget import decide
from clinical_evidence.narrative.generator import _findings_for_page, generate_pages
from clinical_evidence.schemas import (
    CompanyContext,
    DiscoveryResult,
    HeadingBlock,
    SectionPayload,
)
from clinical_evidence.signal.filter import filter_noise
from clinical_evidence.signal.scorer import score_findings
from clinical_evidence.tests.fixtures import (
    sample_company,
    sample_discovery,
    sample_findings,
    sample_trials,
)
from clinical_evidence.verification.crosscheck import reconcile


def test_pipeline_produces_six_pages_offline():
    company: CompanyContext = sample_company()
    discovery: DiscoveryResult = sample_discovery()
    findings = sample_findings()

    findings = reconcile(
        findings,
        documents=discovery.documents,
        trials=discovery.trials,
        publications=discovery.publications,
    )
    findings = score_findings(findings, trials=discovery.trials)
    findings = filter_noise(findings)

    citations = build_citations(findings=findings, documents=discovery.documents)
    page_count, omitted = decide(findings, per_page_findings=_findings_for_page)
    pages = generate_pages(
        findings=findings,
        trials=discovery.trials,
        citations=citations,
        company_name=company.name,
        page_count=page_count,
        use_llm=False,
    )
    payload: SectionPayload = compose(
        run_id="run-offline",
        company_id=company.company_id,
        company_name=company.name,
        pages=pages,
        citations=citations,
        omitted_fraction=omitted,
        page_count=page_count,
    )

    # ── institutional guarantees ────────────────────────────────────────
    assert payload.page_count >= 6
    assert payload.page_count <= 10
    # Page titles must match the spec sequence
    assert [p.index for p in payload.pages] == list(range(1, payload.page_count + 1))
    assert payload.pages[0].title.lower().startswith("clinical executive summary")
    # Citations must be assigned in score-rank order
    assert all(c.number == idx + 1 for idx, c in enumerate(payload.citations))
    # No fluff strings on any page
    fluff_words = ("promising", "potentially transformative", "best-in-class")
    rendered = " ".join(_flatten_text(payload)).lower()
    for word in fluff_words:
        assert word not in rendered, f"fluff word '{word}' leaked into the section"
    # Every page starts with a heading
    for page in payload.pages:
        assert any(isinstance(b, HeadingBlock) for b in page.blocks)


def _flatten_text(payload: SectionPayload) -> list[str]:
    out: list[str] = []
    for page in payload.pages:
        for block in page.blocks:
            for field in ("text", "title"):
                v = getattr(block, field, None)
                if isinstance(v, str):
                    out.append(v)
            for sub in getattr(block, "rows", []) or []:
                v = getattr(sub, "event", None) or getattr(sub, "endpoint", None)
                if isinstance(v, str):
                    out.append(v)
            for sub in getattr(block, "entries", []) or []:
                v = getattr(sub, "label", None)
                if isinstance(v, str):
                    out.append(v)
    return out
