"""Family construction over PatentRecord lists.

Groups records into families using:
1. explicit parent_publication_numbers when present;
2. shared earliest_priority_date + overlapping CPC subclasses + title
   similarity as a heuristic fallback.

The family is the diligence unit: moat, FTO, and expiration logic
operate on families, not single filings.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import date

from medfuel.ip.models import (
    ClaimType,
    FamilyJurisdictionCoverage,
    FilingKind,
    LegalStatus,
    PatentFamily,
    PatentRecord,
)


def build_families(records: list[PatentRecord]) -> list[PatentFamily]:
    """Group records into PatentFamily instances.

    Records with explicit parent links collapse into one family;
    remaining records cluster on (priority_year, normalized title prefix).
    Single-member families are still emitted — they keep the downstream
    framework engines uniform.
    """
    if not records:
        return []

    groups: list[list[PatentRecord]] = []
    by_pub: dict[str, PatentRecord] = {
        r.publication_number: r for r in records if r.publication_number
    }
    placed: set[str] = set()

    # First pass: explicit parent references.
    for rec in records:
        if rec.patent_id in placed:
            continue
        cluster = _walk_parents(rec, by_pub, placed)
        if len(cluster) > 1:
            for r in cluster:
                placed.add(r.patent_id)
            groups.append(cluster)

    # Second pass: heuristic clustering for remaining.
    remaining = [r for r in records if r.patent_id not in placed]
    bucketed: dict[tuple, list[PatentRecord]] = defaultdict(list)
    for r in remaining:
        bucketed[_heuristic_key(r)].append(r)
    for cluster in bucketed.values():
        groups.append(cluster)

    return [_assemble(g) for g in groups]


def _walk_parents(
    seed: PatentRecord,
    by_pub: dict[str, PatentRecord],
    placed: set[str],
) -> list[PatentRecord]:
    seen: dict[str, PatentRecord] = {seed.patent_id: seed}
    queue: list[PatentRecord] = [seed]
    while queue:
        current = queue.pop()
        for parent_pub in current.parent_publication_numbers:
            parent = by_pub.get(parent_pub)
            if parent and parent.patent_id not in seen and parent.patent_id not in placed:
                seen[parent.patent_id] = parent
                queue.append(parent)
        # Forward: collect any record pointing back at this one.
        for other in by_pub.values():
            if other.patent_id in seen or other.patent_id in placed:
                continue
            if current.publication_number and current.publication_number in other.parent_publication_numbers:
                seen[other.patent_id] = other
                queue.append(other)
    return list(seen.values())


_TITLE_NORMALIZE = re.compile(r"[^a-z0-9]+")


def _heuristic_key(rec: PatentRecord) -> tuple:
    title = (rec.title or "").lower()
    title_prefix = " ".join(_TITLE_NORMALIZE.sub(" ", title).split()[:6])
    priority_year = rec.priority_date.year if rec.priority_date else (
        rec.filing_date.year if rec.filing_date else 0
    )
    return (priority_year, title_prefix)


def _assemble(cluster: list[PatentRecord]) -> PatentFamily:
    family_id = f"fam_{uuid.uuid4().hex[:12]}"
    ordered = sorted(
        cluster,
        key=lambda r: (r.priority_date or r.filing_date or date.max),
    )
    head = ordered[0]
    earliest_priority = min(
        (r.priority_date for r in ordered if r.priority_date),
        default=None,
    )
    latest_expiration = max(
        (r.expiration_estimate for r in ordered if r.expiration_estimate),
        default=None,
    )

    coverage_map: dict[str, dict[str, int]] = defaultdict(lambda: {"all": 0, "granted": 0, "pending": 0})
    for r in ordered:
        c = coverage_map[r.jurisdiction]
        c["all"] += 1
        if r.legal_status == LegalStatus.GRANTED:
            c["granted"] += 1
        elif r.legal_status == LegalStatus.PENDING:
            c["pending"] += 1

    coverage = [
        FamilyJurisdictionCoverage(
            jurisdiction=j,
            patent_count=c["all"],
            granted_count=c["granted"],
            pending_count=c["pending"],
        )
        for j, c in coverage_map.items()
    ]

    independent = [
        c for r in ordered for c in r.claims if c.is_independent
    ]
    dominant = _dominant_claim_type(independent)
    fwd = sum(r.forward_citations for r in ordered)
    assignees: list[str] = []
    for r in ordered:
        for a in r.assignees:
            if a not in assignees:
                assignees.append(a)
    for r in ordered:
        r.family_id = family_id

    return PatentFamily(
        family_id=family_id,
        representative_title=head.title or "Untitled family",
        earliest_priority_date=earliest_priority,
        latest_expiration_estimate=latest_expiration,
        members=ordered,
        coverage=coverage,
        continuation_count=sum(1 for r in ordered if r.kind == FilingKind.CONTINUATION),
        divisional_count=sum(1 for r in ordered if r.kind == FilingKind.DIVISIONAL),
        cip_count=sum(1 for r in ordered if r.kind == FilingKind.CONTINUATION_IN_PART),
        independent_claims=independent,
        dominant_claim_type=dominant,
        forward_citation_total=fwd,
        has_composition_claims=any(c.claim_type == ClaimType.COMPOSITION for c in independent),
        has_method_claims=any(c.claim_type == ClaimType.METHOD for c in independent),
        has_device_claims=any(c.claim_type == ClaimType.DEVICE for c in independent),
        has_software_only_claims=(
            bool(independent)
            and all(c.claim_type == ClaimType.SOFTWARE for c in independent)
        ),
        assignees=assignees,
    )


def _dominant_claim_type(claims: list) -> ClaimType:
    if not claims:
        return ClaimType.OTHER
    counts: dict[ClaimType, int] = defaultdict(int)
    for c in claims:
        counts[c.claim_type] += 1
    # COMPOSITION beats METHOD beats DEVICE on ties — that order reflects
    # decreasing design-around difficulty for life-sciences IP.
    priority = [
        ClaimType.COMPOSITION, ClaimType.METHOD, ClaimType.DEVICE,
        ClaimType.PROCESS, ClaimType.USE, ClaimType.SYSTEM,
        ClaimType.SOFTWARE, ClaimType.OTHER,
    ]
    return max(counts.items(), key=lambda kv: (kv[1], -priority.index(kv[0])))[0]
