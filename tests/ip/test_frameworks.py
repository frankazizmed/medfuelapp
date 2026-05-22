from __future__ import annotations

from datetime import date

from medfuel.ip.models import (
    ClaimBreadth,
    ClaimType,
    FamilyJurisdictionCoverage,
    FilingKind,
    IPSourceType,
    LegalStatus,
    PatentClaim,
    PatentFamily,
    PatentRecord,
)
from medfuel.ip.score import (
    HIGH_SIGNAL_THRESHOLD,
    compute_signal_score,
    is_low_signal_family,
    score_all_frameworks,
    score_claim_strength,
    score_commercialization,
    score_competitive_differentiation,
    score_exclusivity,
    score_fto_risk,
    score_moat,
    score_portfolio_quality,
)


def _family(
    *,
    composition: bool = False,
    method: bool = False,
    device: bool = False,
    software_only: bool = False,
    jurisdictions: int = 1,
    members: int = 1,
    granted: int | None = None,
    pending: int = 0,
    forward_citations: int = 5,
    expiration: date | None = None,
    continuations: int = 0,
) -> PatentFamily:
    granted = members if granted is None else granted
    member_records = []
    for i in range(members):
        status = LegalStatus.GRANTED if i < granted else LegalStatus.PENDING
        member_records.append(
            PatentRecord(
                patent_id=f"ip_p{i}",
                publication_number=f"US{1000000+i}B2",
                title="Test patent",
                jurisdiction="US",
                kind=FilingKind.UTILITY if i < members - continuations else FilingKind.CONTINUATION,
                legal_status=status,
                priority_date=date(2018, 1, 1),
                expiration_estimate=expiration,
                forward_citations=forward_citations,
                primary_source=IPSourceType.PATENTSVIEW,
            )
        )
    independent_claims = []
    if composition:
        independent_claims.append(
            PatentClaim(
                claim_number=1,
                text="A composition comprising X.",
                is_independent=True,
                claim_type=ClaimType.COMPOSITION,
                breadth=ClaimBreadth.BROAD,
            )
        )
    if method:
        independent_claims.append(
            PatentClaim(
                claim_number=2,
                text="A method of treating Y comprising administering X.",
                is_independent=True,
                claim_type=ClaimType.METHOD,
                breadth=ClaimBreadth.MODERATE,
            )
        )
    if device:
        independent_claims.append(
            PatentClaim(
                claim_number=3,
                text="A device for measuring X.",
                is_independent=True,
                claim_type=ClaimType.DEVICE,
                breadth=ClaimBreadth.MODERATE,
            )
        )
    if software_only:
        independent_claims = [
            PatentClaim(
                claim_number=1,
                text="A computer-implemented method for X using a neural network.",
                is_independent=True,
                claim_type=ClaimType.SOFTWARE,
                breadth=ClaimBreadth.NARROW,
            )
        ]
    coverage = [
        FamilyJurisdictionCoverage(
            jurisdiction=f"J{i}",
            patent_count=members,
            granted_count=granted,
            pending_count=pending,
        )
        for i in range(jurisdictions)
    ]
    return PatentFamily(
        family_id="fam_test",
        representative_title="Test family",
        earliest_priority_date=date(2018, 1, 1),
        latest_expiration_estimate=expiration,
        members=member_records,
        coverage=coverage,
        continuation_count=continuations,
        divisional_count=0,
        cip_count=0,
        independent_claims=independent_claims,
        dominant_claim_type=(
            ClaimType.COMPOSITION if composition else
            ClaimType.METHOD if method else
            ClaimType.DEVICE if device else
            ClaimType.SOFTWARE if software_only else
            ClaimType.OTHER
        ),
        forward_citation_total=forward_citations * members,
        has_composition_claims=composition,
        has_method_claims=method,
        has_device_claims=device,
        has_software_only_claims=software_only,
    )


def test_composition_family_beats_software_only_on_moat():
    composition = _family(composition=True, method=True, members=3, jurisdictions=3)
    software = _family(software_only=True, members=1)
    assert score_moat(composition) > score_moat(software)
    assert score_claim_strength(composition) > score_claim_strength(software)


def test_exclusivity_increases_with_remaining_term():
    far_future = _family(composition=True, expiration=date.today().replace(year=date.today().year + 15))
    near_expiry = _family(composition=True, expiration=date.today().replace(year=date.today().year + 1))
    assert score_exclusivity(far_future) > score_exclusivity(near_expiry)


def test_fto_risk_drops_with_litigation_or_ptab():
    base = _family(composition=True, members=2, jurisdictions=2)
    base_score = score_fto_risk(base)
    litigated = score_fto_risk(base, active_litigation_count=2, ptab_challenge_count=1)
    assert litigated < base_score


def test_portfolio_quality_penalizes_all_pending():
    pending = _family(composition=True, members=3, granted=0, pending=3)
    granted = _family(composition=True, members=3, granted=3, pending=0)
    assert score_portfolio_quality(granted) > score_portfolio_quality(pending)


def test_compute_signal_score_uses_all_components():
    strong = _family(composition=True, method=True, members=3, jurisdictions=3, expiration=date.today().replace(year=date.today().year + 12))
    weak = _family(software_only=True, members=1, expiration=date.today().replace(year=date.today().year + 2))
    s_strong = score_all_frameworks(strong)
    s_weak = score_all_frameworks(weak)
    assert compute_signal_score(s_strong) > compute_signal_score(s_weak)
    assert compute_signal_score(s_strong) >= HIGH_SIGNAL_THRESHOLD


def test_low_signal_filter_drops_pure_software_narrow():
    weak = _family(software_only=True, members=1)
    scores = score_all_frameworks(weak)
    assert is_low_signal_family(weak, scores) is True


def test_low_signal_filter_keeps_composition_family():
    strong = _family(composition=True, method=True, members=3, jurisdictions=3, expiration=date.today().replace(year=date.today().year + 12))
    scores = score_all_frameworks(strong)
    assert is_low_signal_family(strong, scores) is False


def test_unused_scorers_still_callable():
    fam = _family(composition=True)
    score_commercialization(fam, commercial_keywords=["antibody"])
    score_competitive_differentiation(fam, overlapping_assignees=2, competitor_citation_overlap=4)
