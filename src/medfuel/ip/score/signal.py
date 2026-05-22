"""Cross-framework IP signal score.

Combines the six framework components (plus exclusivity and the
strategic-value synthesis) into one institutional signal score per
family. The layout engine uses this directly to decide who appears
on the 5-page baseline vs. who is compressed into a table.
"""

from __future__ import annotations

from medfuel.ip.models import FrameworkScores, PatentFamily

# Weights tuned for "what an institutional life-sciences IP committee
# would actually care about". Sum to 1.0; kept here as a single edit
# point so future re-balancing is one diff.
SIGNAL_WEIGHTS: dict[str, float] = {
    "claim_strength": 0.18,
    "moat": 0.22,
    "commercialization": 0.18,
    "differentiation": 0.10,
    "fto_risk": 0.12,           # higher = safer; weighted positively
    "portfolio_quality": 0.08,
    "exclusivity": 0.12,
}

HIGH_SIGNAL_THRESHOLD = 65.0
TABLE_ONLY_THRESHOLD = 45.0


def compute_signal_score(scores: FrameworkScores) -> float:
    raw = sum(SIGNAL_WEIGHTS[k] * getattr(scores, k) for k in SIGNAL_WEIGHTS)
    return round(raw, 2)


def family_table_summary(family: PatentFamily, scores: FrameworkScores) -> dict:
    """Compact dict for the portfolio table on page 2."""
    return {
        "family_id": family.family_id,
        "title": family.representative_title[:90],
        "jurisdictions": len(family.coverage),
        "members": len(family.members),
        "earliest_priority": family.earliest_priority_date.isoformat()
        if family.earliest_priority_date
        else None,
        "latest_expiration": family.latest_expiration_estimate.isoformat()
        if family.latest_expiration_estimate
        else None,
        "dominant_claim_type": family.dominant_claim_type.value,
        "claim_strength": scores.claim_strength,
        "moat": scores.moat,
        "commercialization": scores.commercialization,
        "fto_risk": scores.fto_risk,
        "exclusivity": scores.exclusivity,
        "signal_score": compute_signal_score(scores),
    }
