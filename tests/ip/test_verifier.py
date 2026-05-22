from __future__ import annotations

from datetime import date

from medfuel.ip.models import (
    FilingKind,
    IPConfidence,
    IPSourceType,
    IPVerificationState,
    LegalStatus,
    PatentFamily,
    PatentRecord,
)
from medfuel.ip.verify import IPVerifier, classify_family
from medfuel.models.schemas import SourceType


def _family_with_doc(doc_id: str) -> PatentFamily:
    return PatentFamily(
        family_id="fam_test",
        representative_title="t",
        earliest_priority_date=date(2018, 1, 1),
        members=[
            PatentRecord(
                patent_id="ip_x",
                publication_number="US1B2",
                title="t",
                jurisdiction="US",
                kind=FilingKind.UTILITY,
                legal_status=LegalStatus.GRANTED,
                source_doc_ids=[doc_id],
                primary_source=IPSourceType.PATENTSVIEW,
            )
        ],
    )


def test_official_plus_aggregator_yields_high_confidence():
    family = _family_with_doc("src_uspto")
    state, conf = classify_family(
        family=family,
        doc_ranks={"src_uspto": 1, "src_pv": 2},
        primary_sources={
            "src_uspto": SourceType.USPTO,
            "src_pv": SourceType.PATENTSVIEW,
        },
    )
    # one official + one aggregator, but only one doc on the family → MEDIUM
    assert state == IPVerificationState.VERIFIED
    assert conf == IPConfidence.MEDIUM


def test_official_with_assignment_upgrades_to_high():
    family = _family_with_doc("src_uspto")
    state, conf = classify_family(
        family=family,
        doc_ranks={"src_uspto": 1},
        primary_sources={"src_uspto": SourceType.USPTO},
        has_assignment_corroboration=True,
    )
    assert state == IPVerificationState.VERIFIED
    assert conf == IPConfidence.HIGH


def test_aggregator_only_yields_reported():
    family = _family_with_doc("src_pv")
    state, conf = classify_family(
        family=family,
        doc_ranks={"src_pv": 2},
        primary_sources={"src_pv": SourceType.PATENTSVIEW},
    )
    assert state == IPVerificationState.REPORTED
    assert conf == IPConfidence.MEDIUM


def test_low_authority_only_yields_inferred():
    family = _family_with_doc("src_google")
    state, conf = classify_family(
        family=family,
        doc_ranks={"src_google": 3},
        primary_sources={"src_google": SourceType.GOOGLE_PATENTS},
    )
    assert state == IPVerificationState.INFERRED
    assert conf == IPConfidence.LOW


def test_verifier_runs_across_families():
    family = _family_with_doc("src_uspto")
    verifier = IPVerifier()
    out = verifier.verify(
        families=[family],
        doc_ranks={"src_uspto": 1},
        primary_sources={"src_uspto": SourceType.USPTO},
    )
    assert out["fam_test"][0] == IPVerificationState.VERIFIED
