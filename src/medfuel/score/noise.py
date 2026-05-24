from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from medfuel.models import RegulatoryEvent, VerifiedClaim
from medfuel.score.signal import is_critical

# Threshold bands from the design doc. These are ENFORCED here (not just
# referenced): a claim's signal score maps to a tier, and the tier decides
# whether it reaches the narrative, only a supporting table, or nothing.
SCORE_MUST_INCLUDE = 85.0
SCORE_PREFER = 75.0
SCORE_TABLE_ONLY = 55.0

# Company / investor-deck content is capped as a share of narrative claims so
# management framing cannot dominate the regulatory story.
COMPANY_SHARE_CAP = 0.15
# official_rank >= this is company-website / investor-deck tier (see OFFICIAL_RANK).
COMPANY_RANK_FLOOR = 4

DEFAULT_MAX_AGE_YEARS = 10
# Old events are excused from the staleness drop when they anchor current
# exclusivity, labeling, or platform credibility (design carve-out).
_STALE_ANCHOR_TYPES = {"approval", "designation", "patent_event", "label_change"}

_NORM = re.compile(r"[^a-z0-9]+")


class ClaimTier(str, Enum):
    MUST_INCLUDE = "must_include"  # >= 85: must appear in the report if verified
    NARRATIVE = "narrative"  # 75-84: primary narrative unless displaced
    TABLE_ONLY = "table_only"  # 55-74: supporting tables / overflow only
    DROPPED = "dropped"  # < 55 or failed a fluff rule: excluded from the report


@dataclass
class NoiseFilterResult:
    tiers: dict[str, ClaimTier]
    narrative_claim_ids: list[str]
    table_claim_ids: list[str]
    dropped: list[tuple[str, str]] = field(default_factory=list)  # (claim_id, reason)
    company_share: float = 0.0
    stats: dict[str, int] = field(default_factory=dict)

    def kept_claim_ids(self) -> set[str]:
        return set(self.narrative_claim_ids) | set(self.table_claim_ids)

    def report(self) -> dict:
        from collections import Counter

        reason_counts = Counter(reason for _, reason in self.dropped)
        return {
            "company_share": round(self.company_share, 4),
            "company_share_cap": COMPANY_SHARE_CAP,
            **self.stats,
            "dropped_reasons": dict(reason_counts),
        }


def _norm(text: str) -> str:
    return _NORM.sub(" ", text.lower()).strip()


def filter_claims(
    *,
    events: list[RegulatoryEvent],
    claims: list[VerifiedClaim],
    doc_ranks: dict[str, int],
    as_of: date | None = None,
    max_age_years: int = DEFAULT_MAX_AGE_YEARS,
    company_share_cap: float = COMPANY_SHARE_CAP,
) -> NoiseFilterResult:
    """Enforce the design's signal-vs-noise rules before layout.

    Order matters — cheap structural drops first, then dedupe, then the
    score-band tiering, then the company-share cap. Every exclusion is
    recorded with a reason so the report can show what was filtered and why.
    """
    as_of = as_of or date.today()
    by_event = {e.event_id: e for e in events}
    tiers: dict[str, ClaimTier] = {}
    dropped: list[tuple[str, str]] = []

    # --- Rule 1 (no citation) + Rule 2 (stale) -------------------------------
    surviving: list[VerifiedClaim] = []
    for claim in claims:
        event = by_event.get(claim.event_id)
        if event is None:
            tiers[claim.claim_id] = ClaimTier.DROPPED
            dropped.append((claim.claim_id, "orphan_no_event"))
            continue
        if not claim.source_doc_ids:
            tiers[claim.claim_id] = ClaimTier.DROPPED
            dropped.append((claim.claim_id, "no_citation"))
            continue
        age_years = (as_of - event.event_date).days / 365.25
        if age_years > max_age_years and event.event_type not in _STALE_ANCHOR_TYPES:
            tiers[claim.claim_id] = ClaimTier.DROPPED
            dropped.append((claim.claim_id, "stale_gt_max_age"))
            continue
        surviving.append(claim)

    # --- Rule 3 (cosmetic-duplicate suppression) -----------------------------
    groups: dict[str, list[VerifiedClaim]] = {}
    for claim in surviving:
        groups.setdefault(_norm(by_event[claim.event_id].summary), []).append(claim)
    deduped: list[VerifiedClaim] = []
    for group in groups.values():
        if len(group) == 1:
            deduped.append(group[0])
            continue
        group.sort(
            key=lambda c: (c.signal_score, by_event[c.event_id].evidence_strength),
            reverse=True,
        )
        deduped.append(group[0])
        for loser in group[1:]:
            tiers[loser.claim_id] = ClaimTier.DROPPED
            dropped.append((loser.claim_id, "cosmetic_duplicate"))

    # --- Score-band tiering --------------------------------------------------
    for claim in deduped:
        if claim.signal_score >= SCORE_MUST_INCLUDE:
            tiers[claim.claim_id] = ClaimTier.MUST_INCLUDE
        elif claim.signal_score >= SCORE_PREFER:
            tiers[claim.claim_id] = ClaimTier.NARRATIVE
        elif claim.signal_score >= SCORE_TABLE_ONLY:
            tiers[claim.claim_id] = ClaimTier.TABLE_ONLY
        elif is_critical(by_event[claim.event_id]):
            # Sub-threshold but critical: keep as table context for chronology /
            # contradiction safety rather than dropping outright.
            tiers[claim.claim_id] = ClaimTier.TABLE_ONLY
        else:
            tiers[claim.claim_id] = ClaimTier.DROPPED
            dropped.append((claim.claim_id, "below_threshold"))

    claim_by_id = {c.claim_id: c for c in deduped}

    def _is_company_only(claim: VerifiedClaim) -> bool:
        return all(
            doc_ranks.get(sid, COMPANY_RANK_FLOOR) >= COMPANY_RANK_FLOOR
            for sid in claim.source_doc_ids
        )

    # --- Company / deck share cap on narrative claims ------------------------
    narrative_ids = [
        cid
        for cid in claim_by_id
        if tiers[cid] in (ClaimTier.MUST_INCLUDE, ClaimTier.NARRATIVE)
    ]
    company_narr = [cid for cid in narrative_ids if _is_company_only(claim_by_id[cid])]
    demoted = 0
    if narrative_ids:
        share = len(company_narr) / len(narrative_ids)
        if share > company_share_cap:
            allowed = int(company_share_cap * len(narrative_ids))
            company_narr.sort(key=lambda cid: claim_by_id[cid].signal_score)
            for cid in company_narr[: max(0, len(company_narr) - allowed)]:
                tiers[cid] = ClaimTier.TABLE_ONLY
                demoted += 1

    # --- Final buckets + stats ----------------------------------------------
    narrative_claim_ids = [
        cid
        for cid, t in tiers.items()
        if t in (ClaimTier.MUST_INCLUDE, ClaimTier.NARRATIVE)
    ]
    table_claim_ids = [cid for cid, t in tiers.items() if t == ClaimTier.TABLE_ONLY]
    final_company = [
        cid
        for cid in narrative_claim_ids
        if cid in claim_by_id and _is_company_only(claim_by_id[cid])
    ]
    company_share = (
        len(final_company) / len(narrative_claim_ids) if narrative_claim_ids else 0.0
    )

    stats = {
        "input": len(claims),
        "must_include": sum(1 for t in tiers.values() if t == ClaimTier.MUST_INCLUDE),
        "narrative": sum(1 for t in tiers.values() if t == ClaimTier.NARRATIVE),
        "table_only": sum(1 for t in tiers.values() if t == ClaimTier.TABLE_ONLY),
        "dropped": sum(1 for t in tiers.values() if t == ClaimTier.DROPPED),
        "company_demoted": demoted,
    }

    return NoiseFilterResult(
        tiers=tiers,
        narrative_claim_ids=narrative_claim_ids,
        table_claim_ids=table_claim_ids,
        dropped=dropped,
        company_share=company_share,
        stats=stats,
    )
