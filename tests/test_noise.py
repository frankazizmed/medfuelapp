from __future__ import annotations

from datetime import date

from medfuel.models import (
    Confidence,
    RegulatoryEvent,
    VerificationState,
    VerifiedClaim,
)
from medfuel.score.noise import ClaimTier, filter_claims

AS_OF = date(2026, 5, 24)


def _event(
    event_id: str,
    event_type: str = "trial_update",
    *,
    event_date: date = date(2025, 1, 1),
    summary: str | None = None,
    evidence: int = 4,
) -> RegulatoryEvent:
    return RegulatoryEvent(
        event_id=event_id,
        company_id="cmp_1",
        agency="FDA",
        jurisdiction="US",
        event_type=event_type,  # type: ignore[arg-type]
        status="status",
        event_date=event_date,
        summary=summary or f"{event_type} {event_id}",
        investor_importance=3,
        evidence_strength=evidence,
        source_doc_ids=[f"src_{event_id}"],
    )


def _claim(
    claim_id: str,
    event: RegulatoryEvent,
    score: float,
    *,
    source_doc_ids: list[str] | None = None,
) -> VerifiedClaim:
    return VerifiedClaim(
        claim_id=claim_id,
        event_id=event.event_id,
        text=event.summary,
        verification_state=VerificationState.VERIFIED,
        confidence=Confidence.HIGH,
        source_doc_ids=source_doc_ids if source_doc_ids is not None else event.source_doc_ids,
        citation_numbers=[],
        signal_score=score,
    )


def test_score_bands_map_to_tiers():
    e_must = _event("must", "approval")
    e_narr = _event("narr", "trial_update")
    e_table = _event("table", "trial_update")
    e_drop = _event("drop", "trial_update")
    events = [e_must, e_narr, e_table, e_drop]
    claims = [
        _claim("c_must", e_must, 90.0),
        _claim("c_narr", e_narr, 80.0),
        _claim("c_table", e_table, 60.0),
        _claim("c_drop", e_drop, 40.0),
    ]
    ranks = {sid: 1 for c in claims for sid in c.source_doc_ids}
    result = filter_claims(events=events, claims=claims, doc_ranks=ranks, as_of=AS_OF)

    assert result.tiers["c_must"] == ClaimTier.MUST_INCLUDE
    assert result.tiers["c_narr"] == ClaimTier.NARRATIVE
    assert result.tiers["c_table"] == ClaimTier.TABLE_ONLY
    assert result.tiers["c_drop"] == ClaimTier.DROPPED
    assert ("c_drop", "below_threshold") in result.dropped
    assert set(result.narrative_claim_ids) == {"c_must", "c_narr"}
    assert result.table_claim_ids == ["c_table"]


def test_sub_threshold_critical_kept_as_table_context():
    # A critical event below 55 is retained as table context, not dropped.
    e = _event("warn", "warning")
    claims = [_claim("c_warn", e, 40.0)]
    ranks = {sid: 1 for sid in e.source_doc_ids}
    result = filter_claims(events=[e], claims=claims, doc_ranks=ranks, as_of=AS_OF)
    assert result.tiers["c_warn"] == ClaimTier.TABLE_ONLY
    assert "c_warn" not in dict(result.dropped)


def test_no_citation_claim_is_dropped():
    e = _event("x", "approval")
    claims = [_claim("c_x", e, 95.0, source_doc_ids=[])]
    result = filter_claims(events=[e], claims=claims, doc_ranks={}, as_of=AS_OF)
    assert result.tiers["c_x"] == ClaimTier.DROPPED
    assert ("c_x", "no_citation") in result.dropped


def test_stale_event_dropped_unless_anchor():
    old = date(2010, 1, 1)  # ~16 years before AS_OF
    e_trial = _event("t", "trial_update", event_date=old)
    e_appr = _event("a", "approval", event_date=old)  # anchor type, excused
    claims = [_claim("c_t", e_trial, 90.0), _claim("c_a", e_appr, 90.0)]
    ranks = {sid: 1 for c in claims for sid in c.source_doc_ids}
    result = filter_claims(
        events=[e_trial, e_appr], claims=claims, doc_ranks=ranks, as_of=AS_OF
    )
    assert result.tiers["c_t"] == ClaimTier.DROPPED
    assert ("c_t", "stale_gt_max_age") in result.dropped
    # approval anchors exclusivity/labeling, so it survives despite age.
    assert result.tiers["c_a"] == ClaimTier.MUST_INCLUDE


def test_cosmetic_duplicates_collapse_to_highest_evidence():
    e1 = _event("d1", "approval", summary="FDA approved Acmenil on 2025-01-15.", evidence=5)
    e2 = _event("d2", "approval", summary="FDA approved  ACMENIL on 2025-01-15!", evidence=3)
    claims = [_claim("c1", e1, 90.0), _claim("c2", e2, 88.0)]
    ranks = {sid: 1 for c in claims for sid in c.source_doc_ids}
    result = filter_claims(events=[e1, e2], claims=claims, doc_ranks=ranks, as_of=AS_OF)
    # Same normalized summary -> keep the higher-score/evidence claim, drop the other.
    assert result.tiers["c1"] == ClaimTier.MUST_INCLUDE
    assert result.tiers["c2"] == ClaimTier.DROPPED
    assert ("c2", "cosmetic_duplicate") in result.dropped


def test_company_share_cap_demotes_excess_company_claims():
    # 1 official narrative claim + 4 company-only narrative claims => company
    # share 80% >> 15% cap, so company claims get demoted to table_only.
    official = _event("off", "approval", summary="official approval")
    official_claim = _claim("c_off", official, 90.0, source_doc_ids=["src_off"])
    company_events = [
        _event(f"co{i}", "designation", summary=f"company designation {i}")
        for i in range(4)
    ]
    company_claims = [
        _claim(f"c_co{i}", ev, 80.0, source_doc_ids=[f"src_co{i}"])
        for i, ev in enumerate(company_events)
    ]
    events = [official, *company_events]
    claims = [official_claim, *company_claims]
    ranks = {"src_off": 1}
    for i in range(4):
        ranks[f"src_co{i}"] = 4  # company tier

    result = filter_claims(events=events, claims=claims, doc_ranks=ranks, as_of=AS_OF)
    # Official claim stays in the narrative.
    assert result.tiers["c_off"] in (ClaimTier.NARRATIVE, ClaimTier.MUST_INCLUDE)
    # At least three company claims demoted to table_only to honour the 15% cap.
    demoted = [cid for cid in result.tiers if cid.startswith("c_co") and result.tiers[cid] == ClaimTier.TABLE_ONLY]
    assert len(demoted) >= 3
    assert result.company_share <= 0.15 + 1e-9
    assert result.stats["company_demoted"] >= 3


def test_report_includes_noise_breakdown():
    e_keep = _event("k", "approval")
    e_drop = _event("d", "trial_update")
    claims = [_claim("c_k", e_keep, 90.0), _claim("c_d", e_drop, 30.0)]
    ranks = {sid: 1 for c in claims for sid in c.source_doc_ids}
    result = filter_claims(events=[e_keep, e_drop], claims=claims, doc_ranks=ranks, as_of=AS_OF)
    report = result.report()
    assert report["input"] == 2
    assert report["dropped"] == 1
    assert report["dropped_reasons"]["below_threshold"] == 1
    assert report["company_share_cap"] == 0.15
