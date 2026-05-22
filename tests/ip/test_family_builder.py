from __future__ import annotations

from datetime import date

from medfuel.ip.extract.family_builder import build_families
from medfuel.ip.models import (
    ClaimType,
    FilingKind,
    IPSourceType,
    LegalStatus,
    PatentClaim,
    PatentRecord,
)


def _patent(
    pub: str,
    *,
    title: str = "Antibody X composition",
    priority: date | None = None,
    parents: list[str] | None = None,
    kind: FilingKind = FilingKind.UTILITY,
    juris: str = "US",
    claims: list[PatentClaim] | None = None,
) -> PatentRecord:
    return PatentRecord(
        patent_id=f"ip_{pub}",
        publication_number=pub,
        title=title,
        jurisdiction=juris,
        kind=kind,
        priority_date=priority or date(2018, 1, 1),
        legal_status=LegalStatus.GRANTED,
        parent_publication_numbers=parents or [],
        claims=claims or [],
        primary_source=IPSourceType.PATENTSVIEW,
    )


def test_build_families_clusters_by_parent_reference():
    parent = _patent("US10000001B2", priority=date(2018, 1, 1))
    child = _patent(
        "US10500001B2",
        priority=date(2019, 6, 1),
        parents=["US10000001B2"],
        kind=FilingKind.CONTINUATION,
    )
    grandchild = _patent(
        "US10800001B2",
        priority=date(2020, 6, 1),
        parents=["US10500001B2"],
        kind=FilingKind.DIVISIONAL,
    )
    unrelated = _patent(
        "US20000001B2",
        title="Cell line for X",
        priority=date(2017, 3, 1),
    )

    families = build_families([parent, child, grandchild, unrelated])
    by_size = sorted([len(f.members) for f in families], reverse=True)
    assert by_size[0] == 3
    big = next(f for f in families if len(f.members) == 3)
    assert big.continuation_count == 1
    assert big.divisional_count == 1
    assert big.earliest_priority_date == date(2018, 1, 1)


def test_build_families_marks_composition_and_dominant_type():
    comp_claim = PatentClaim(
        claim_number=1,
        text="A composition comprising compound X.",
        is_independent=True,
        claim_type=ClaimType.COMPOSITION,
    )
    method_claim = PatentClaim(
        claim_number=1,
        text="A method of treating Y comprising administering compound X.",
        is_independent=True,
        claim_type=ClaimType.METHOD,
    )
    p = _patent("US10000001B2", claims=[comp_claim, method_claim])
    families = build_families([p])
    assert len(families) == 1
    f = families[0]
    assert f.has_composition_claims is True
    assert f.has_method_claims is True
    assert f.dominant_claim_type == ClaimType.COMPOSITION  # composition wins priority
