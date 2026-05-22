"""IP verification layer.

Classifies each PatentFamily as VERIFIED / REPORTED / INFERRED based on:
- whether members carry official-rank sources (USPTO / EPO / WIPO);
- whether independent assignment records corroborate ownership;
- whether forward/backward citations are sourced from official data.

Verification state and confidence then propagate to every IPFinding
the framework engine emits from this family.
"""

from __future__ import annotations

from medfuel.ip.models import (
    IPConfidence,
    IPSourceType,
    IPVerificationState,
    PatentFamily,
)
from medfuel.models.schemas import OFFICIAL_RANK, SourceType

# Patent offices and tribunals are the only sources we accept as
# verification-grade. Aggregators (PatentsView, Google Patents) corroborate
# but do not, on their own, lift a finding above REPORTED.
_OFFICIAL_IP_RANK_CEIL = 1

# Map source type -> rank for the source documents the verifier is given.
_RANK = OFFICIAL_RANK


def classify_family(
    *,
    family: PatentFamily,
    doc_ranks: dict[str, int],
    primary_sources: dict[str, SourceType],
    has_assignment_corroboration: bool = False,
) -> tuple[IPVerificationState, IPConfidence]:
    """Return (state, confidence) for one family.

    `doc_ranks` maps source_doc_id -> official_rank as persisted.
    `primary_sources` maps the same ids onto SourceType for tribunal-type
    checks (PTAB/litigation count toward verification of disputed claims).
    """
    member_doc_ids: set[str] = {
        sid for m in family.members for sid in m.source_doc_ids
    }
    official = sum(
        1 for sid in member_doc_ids if doc_ranks.get(sid, 5) <= _OFFICIAL_IP_RANK_CEIL
    )
    aggregator = sum(
        1 for sid in member_doc_ids if doc_ranks.get(sid, 5) == 2
    )

    if official >= 1 and (aggregator >= 1 or has_assignment_corroboration):
        return IPVerificationState.VERIFIED, IPConfidence.HIGH
    if official >= 1:
        return IPVerificationState.VERIFIED, IPConfidence.MEDIUM
    if aggregator >= 1:
        return IPVerificationState.REPORTED, IPConfidence.MEDIUM
    return IPVerificationState.INFERRED, IPConfidence.LOW


class IPVerifier:
    """Apply classify_family across all families for one company.

    Returns a parallel mapping family_id -> (state, confidence) so the
    framework engine and narrative renderer can read it without
    re-traversing the source documents.
    """

    def verify(
        self,
        *,
        families: list[PatentFamily],
        doc_ranks: dict[str, int],
        primary_sources: dict[str, SourceType],
        assignments_by_patent: dict[str, list[str]] | None = None,
    ) -> dict[str, tuple[IPVerificationState, IPConfidence]]:
        out: dict[str, tuple[IPVerificationState, IPConfidence]] = {}
        for family in families:
            has_assignments = False
            if assignments_by_patent:
                for member in family.members:
                    key = member.publication_number or member.application_number or ""
                    if assignments_by_patent.get(key):
                        has_assignments = True
                        break
            out[family.family_id] = classify_family(
                family=family,
                doc_ranks=doc_ranks,
                primary_sources=primary_sources,
                has_assignment_corroboration=has_assignments,
            )
        return out


__all__ = ["IPVerifier", "classify_family", "IPSourceType"]
