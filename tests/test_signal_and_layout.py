from __future__ import annotations

from datetime import date

from medfuel.models import (
    Confidence,
    RegulatoryEvent,
    VerificationState,
    VerifiedClaim,
)
from medfuel.render.layout import (
    HIGH_SIGNAL_THRESHOLD,
    plan_layout,
)
from medfuel.score.signal import compute_signal_score, is_critical


def _event(
    event_id: str,
    event_type: str,
    *,
    investor_importance: int = 5,
    evidence_strength: int = 5,
    sources: int = 2,
    event_date: date | None = None,
) -> RegulatoryEvent:
    return RegulatoryEvent(
        event_id=event_id,
        company_id="cmp_1",
        agency="FDA",
        jurisdiction="US",
        event_type=event_type,  # type: ignore[arg-type]
        status="status",
        event_date=event_date or date(2024, 1, 1),
        summary=f"{event_type} for asset {event_id}",
        investor_importance=investor_importance,
        evidence_strength=evidence_strength,
        source_doc_ids=[f"src_{i}_{event_id}" for i in range(sources)],
    )


def _claim(claim_id: str, event: RegulatoryEvent, score: float | None = None) -> VerifiedClaim:
    return VerifiedClaim(
        claim_id=claim_id,
        event_id=event.event_id,
        text=event.summary,
        verification_state=VerificationState.VERIFIED,
        confidence=Confidence.HIGH,
        source_doc_ids=event.source_doc_ids,
        citation_numbers=[],
        signal_score=score if score is not None else compute_signal_score(event),
    )


def test_signal_score_higher_for_critical_corroborated_events():
    approval = _event("evt_a", "approval", investor_importance=5, evidence_strength=5, sources=3)
    patent = _event("evt_b", "patent_event", investor_importance=2, evidence_strength=3, sources=1)
    assert compute_signal_score(approval) > compute_signal_score(patent)
    assert is_critical(approval)
    assert not is_critical(patent)


def test_layout_keeps_six_pages_when_no_critical_omitted():
    events = [
        _event("e1", "approval"),
        _event("e2", "trial_update", investor_importance=3, evidence_strength=4),
        _event("e3", "warning", investor_importance=4, evidence_strength=5),
    ]
    claims = [_claim(f"c{i}", e) for i, e in enumerate(events)]
    layout = plan_layout(events=events, claims=claims, requested_pages=6, max_pages=10)
    assert layout.pages_rendered == 6
    assert layout.adaptive_expansion_triggered is False
    assert {s.slug for s in layout.sections} == {
        "executive_summary",
        "pathway_matrix",
        "timeline",
        "trials_and_evidence",
        "safety_quality_compliance",
        "implications_and_watchlist",
    }


def test_layout_expands_when_critical_items_would_be_omitted():
    # Build more critical items than the six-page baseline can absorb.
    # Baseline capacity is ~24 placements; 40 high-signal items forces expansion.
    events = [
        _event(f"e_app_{i}", "approval", investor_importance=5, evidence_strength=5, sources=3)
        for i in range(20)
    ] + [
        _event(f"e_warn_{i}", "warning", investor_importance=5, evidence_strength=5, sources=3)
        for i in range(20)
    ]
    claims = [_claim(f"c_{i}", e) for i, e in enumerate(events)]
    # Sanity: all claims are above the high-signal threshold.
    assert all(c.signal_score >= HIGH_SIGNAL_THRESHOLD for c in claims)

    layout = plan_layout(events=events, claims=claims, requested_pages=6, max_pages=10)
    assert layout.adaptive_expansion_triggered is True
    assert 6 < layout.pages_rendered <= 10
    assert any("expanded" in r for r in layout.expansion_reasons)


def test_layout_caps_at_max_pages():
    # Far more high-signal claims than 10 pages can absorb.
    events = [_event(f"e{i}", "approval", sources=3) for i in range(60)]
    claims = [_claim(f"c{i}", e) for i, e in enumerate(events)]
    layout = plan_layout(events=events, claims=claims, requested_pages=6, max_pages=10)
    assert layout.pages_rendered == 10
