"""Signal-vs-noise filter.

The core differentiator from generic AI summarizers: aggressively
drop low-value filings so the narrative doesn't waste tokens on them.

Returns True for families that should be COMPRESSED INTO A TABLE or
DROPPED, not given prose treatment.
"""

from __future__ import annotations

from medfuel.ip.models import FrameworkScores, LegalStatus, PatentFamily
from medfuel.ip.score.signal import TABLE_ONLY_THRESHOLD, compute_signal_score


def is_low_signal_family(family: PatentFamily, scores: FrameworkScores) -> bool:
    if compute_signal_score(scores) < TABLE_ONLY_THRESHOLD:
        return True

    # Provisional-only or abandoned-only families are noise.
    all_abandoned = bool(family.members) and all(
        m.legal_status in (LegalStatus.ABANDONED, LegalStatus.LAPSED, LegalStatus.EXPIRED)
        for m in family.members
    )
    if all_abandoned:
        return True

    # Pure software-claims family with no independent breadth → noise.
    if family.has_software_only_claims and not family.has_composition_claims:
        narrow_claims = all(
            c.breadth.value == "narrow" for c in family.independent_claims
        )
        if narrow_claims:
            return True

    # No independent claims at all → cannot anchor a finding.
    return not family.independent_claims and not family.members
