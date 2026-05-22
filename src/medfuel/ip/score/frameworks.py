"""Six-framework scoring engine.

Each scorer turns one PatentFamily (plus optional context) into a
0-100 component score. The composite signal score (see signal.py)
then combines them with weights that match the design rubric.

The scorers are intentionally rule-driven so the report can defend
every number against citations. An LLM adjudicator can replace
individual components later without disturbing the public interface.
"""

from __future__ import annotations

from datetime import date

from medfuel.ip.models import (
    ClaimBreadth,
    ClaimType,
    FrameworkScores,
    LegalStatus,
    PatentFamily,
)

# --------------------------------------------------------------------------- A. claim strength


def score_claim_strength(family: PatentFamily) -> float:
    """Defensibility from claim structure alone.

    Drivers:
    - any granted broad independent claim → big lift;
    - composition or method-of-use claims → strong (life-sci context);
    - amendment narrowing implied by long claims → small penalty;
    - software-only independents → cap below moderate (easier to design around).
    """
    if not family.independent_claims:
        return 25.0
    score = 40.0
    for claim in family.independent_claims:
        if claim.breadth == ClaimBreadth.BROAD:
            score += 12
        elif claim.breadth == ClaimBreadth.NARROW:
            score -= 6
        if claim.claim_type == ClaimType.COMPOSITION:
            score += 14
        elif claim.claim_type in (ClaimType.METHOD, ClaimType.USE):
            score += 8
        elif claim.claim_type == ClaimType.DEVICE:
            score += 5
        elif claim.claim_type == ClaimType.SOFTWARE:
            score -= 4
    score = _clamp(score, lower=10, upper=98)
    if family.has_software_only_claims and not family.has_composition_claims:
        score = min(score, 55.0)
    return round(score, 1)


# --------------------------------------------------------------------------- B. moat


def score_moat(family: PatentFamily) -> float:
    """Difficulty of competing around the family.

    Drivers:
    - composition + method coverage on same family;
    - large family size + multi-jurisdiction footprint;
    - continuation strategy (pending children = future flexibility);
    - high forward-citation count signals defensibility against design-arounds.
    """
    base = 35.0
    if family.has_composition_claims and family.has_method_claims:
        base += 20
    elif family.has_composition_claims:
        base += 12
    elif family.has_method_claims:
        base += 8

    jurisdictions = len(family.coverage)
    if jurisdictions >= 3:
        base += 10
    elif jurisdictions == 2:
        base += 5

    children = family.continuation_count + family.divisional_count + family.cip_count
    if children >= 3:
        base += 10
    elif children >= 1:
        base += 5

    if family.forward_citation_total >= 25:
        base += 10
    elif family.forward_citation_total >= 5:
        base += 4

    if family.has_software_only_claims:
        base -= 8
    return round(_clamp(base, lower=10, upper=98), 1)


# --------------------------------------------------------------------------- C. commercialization


def score_commercialization(
    family: PatentFamily,
    *,
    commercial_keywords: list[str] | None = None,
) -> float:
    """How well the family protects the commercial product.

    Without an explicit commercial-product spec the scorer relies on:
    - composition + device combinations (typical "product cover");
    - manufacturing-process claims (process protection);
    - presence of any commercial keyword match in titles or claim text.
    """
    base = 35.0
    if family.has_composition_claims and family.has_device_claims:
        base += 22
    elif family.has_composition_claims and family.has_method_claims:
        # Composition + method-of-use is the classic biologics product moat.
        base += 20
    elif family.has_composition_claims:
        base += 12
    elif family.has_method_claims:
        base += 6
    if any(c.claim_type == ClaimType.PROCESS for c in family.independent_claims):
        base += 8
    if commercial_keywords:
        blob = (
            family.representative_title
            + " "
            + " ".join(c.text for c in family.independent_claims)
        ).lower()
        if any(k.lower() in blob for k in commercial_keywords):
            base += 12
    if family.has_software_only_claims:
        base -= 6
    return round(_clamp(base, lower=15, upper=95), 1)


# --------------------------------------------------------------------------- D. competitive differentiation


def score_competitive_differentiation(
    family: PatentFamily,
    *,
    overlapping_assignees: int = 0,
    competitor_citation_overlap: int = 0,
) -> float:
    """How distinct the family looks vs the competitive set.

    Drivers:
    - no overlapping assignees on the cited art → cleaner white space;
    - heavy competitor forward-citation overlap → less differentiation;
    - distinctive claim composition (CPC concentration) → modest lift.
    """
    base = 55.0
    base -= min(overlapping_assignees, 5) * 4
    base -= min(competitor_citation_overlap, 10) * 2
    if family.forward_citation_total >= 10:
        base += 6
    if family.has_composition_claims:
        base += 6
    return round(_clamp(base, lower=10, upper=95), 1)


# --------------------------------------------------------------------------- E. FTO risk


def score_fto_risk(
    family: PatentFamily,
    *,
    blocking_patent_count: int = 0,
    active_litigation_count: int = 0,
    ptab_challenge_count: int = 0,
) -> float:
    """Inverted-risk scale: lower number = greater risk.

    A composite "you can operate freely here" score. Litigation or PTAB
    challenges on the family's own patents drop the score sharply.
    """
    base = 70.0
    base -= min(blocking_patent_count, 10) * 4
    base -= active_litigation_count * 8
    base -= ptab_challenge_count * 6
    if family.has_software_only_claims:
        base -= 6
    return round(_clamp(base, lower=5, upper=95), 1)


# --------------------------------------------------------------------------- F. portfolio quality


def score_portfolio_quality(family: PatentFamily) -> float:
    """Institutional sophistication signal.

    Drivers:
    - multi-jurisdiction coverage;
    - mix of utility + continuation strategy (not provisional-only);
    - mature grants vs heavy pending share;
    - granted independents > 1 (suggests claim depth, not single point).
    """
    base = 30.0
    base += min(len(family.coverage), 4) * 6
    granted = sum(1 for m in family.members if m.legal_status == LegalStatus.GRANTED)
    pending = sum(1 for m in family.members if m.legal_status == LegalStatus.PENDING)
    total = max(len(family.members), 1)
    grant_ratio = granted / total
    base += grant_ratio * 18
    if family.continuation_count >= 1 or family.divisional_count >= 1:
        base += 8
    if family.independent_claims and len(family.independent_claims) >= 2:
        base += 8
    if pending == total and total >= 2:
        # Provisional-heavy / pending-heavy portfolio = weak signal.
        base -= 10
    return round(_clamp(base, lower=10, upper=95), 1)


# --------------------------------------------------------------------------- G. exclusivity duration


def score_exclusivity(family: PatentFamily, *, today: date | None = None) -> float:
    """Translate remaining patent life into a 0-100 score.

    20 years remaining = 100; 0 years = 0; linear in between. Uses the
    family's latest expiration estimate to credit lifecycle management.
    """
    today = today or date.today()
    end = family.latest_expiration_estimate
    if end is None:
        return 30.0
    years_remaining = (end - today).days / 365.25
    if years_remaining <= 0:
        return 0.0
    return round(_clamp(years_remaining / 20.0 * 100.0, lower=0, upper=100), 1)


# --------------------------------------------------------------------------- H. strategic value (composite)


def score_strategic_value(family: PatentFamily, scores: FrameworkScores) -> float:
    """Higher-level synthesis used as a tie-breaker for ranking.

    Weights the rest of the framework outputs by importance to
    institutional diligence (moat + commercialization + exclusivity
    matter most for valuation).
    """
    weighted = (
        0.30 * scores.moat
        + 0.25 * scores.commercialization
        + 0.20 * scores.exclusivity
        + 0.15 * scores.claim_strength
        + 0.10 * scores.differentiation
    )
    return round(_clamp(weighted, lower=0, upper=100), 1)


# --------------------------------------------------------------------------- composite helper


def score_all_frameworks(
    family: PatentFamily,
    *,
    blocking_patent_count: int = 0,
    active_litigation_count: int = 0,
    ptab_challenge_count: int = 0,
    overlapping_assignees: int = 0,
    competitor_citation_overlap: int = 0,
    commercial_keywords: list[str] | None = None,
    today: date | None = None,
) -> FrameworkScores:
    """One-shot helper to compute every component and return them."""
    cs = score_claim_strength(family)
    moat = score_moat(family)
    comm = score_commercialization(family, commercial_keywords=commercial_keywords)
    diff = score_competitive_differentiation(
        family,
        overlapping_assignees=overlapping_assignees,
        competitor_citation_overlap=competitor_citation_overlap,
    )
    fto = score_fto_risk(
        family,
        blocking_patent_count=blocking_patent_count,
        active_litigation_count=active_litigation_count,
        ptab_challenge_count=ptab_challenge_count,
    )
    pq = score_portfolio_quality(family)
    excl = score_exclusivity(family, today=today)
    base = FrameworkScores(
        claim_strength=cs,
        moat=moat,
        commercialization=comm,
        differentiation=diff,
        fto_risk=fto,
        portfolio_quality=pq,
        exclusivity=excl,
        strategic_value=0,
    )
    base.strategic_value = score_strategic_value(family, base)
    return base


# --------------------------------------------------------------------------- utils


def _clamp(x: float, *, lower: float, upper: float) -> float:
    return max(lower, min(upper, x))
