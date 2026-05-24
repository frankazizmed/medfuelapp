from __future__ import annotations

from datetime import date

from medfuel.extract.dedupe import dedupe_events, event_key
from medfuel.extract.normalize import normalize_agency, normalize_date, resolve_asset
from medfuel.models import CandidateEvent


def test_normalize_date_handles_compact_iso_and_text():
    assert normalize_date("20240115") == date(2024, 1, 15)
    assert normalize_date("2024-08-01") == date(2024, 8, 1)
    assert normalize_date("Mar 15, 2024") == date(2024, 3, 15)
    assert normalize_date("not a date") is None
    assert normalize_date(None) is None


def test_normalize_agency_canonicalizes_common_aliases():
    assert normalize_agency("fda") == "FDA"
    assert normalize_agency("U.S. Food and Drug Administration") == "FDA"
    assert normalize_agency("Pharmaceuticals and Medical Devices Agency") == "PMDA"
    assert normalize_agency("MysteryBoard") == "MysteryBoard"


def test_resolve_asset_strips_marks_and_caches_canonical():
    known: dict[str, str] = {}
    canonical, key = resolve_asset("Examplon®", known_assets=known)
    assert canonical == "Examplon®"
    known[key] = canonical
    canonical2, key2 = resolve_asset("examplon", known_assets=known)
    assert key2 == key
    assert canonical2 == "Examplon®"


def test_dedupe_groups_by_semantic_event_key():
    cand_a = CandidateEvent(
        agency="FDA",
        jurisdiction="US",
        event_type="approval",
        status="AP",
        summary="A",
        event_date=date(2024, 1, 15),
        asset_name="Examplon",
        source_doc_id="src_1",
    )
    cand_b = CandidateEvent(
        agency="FDA",
        jurisdiction="US",
        event_type="approval",
        status="AP",
        summary="B",
        event_date=date(2024, 1, 15),
        asset_name="EXAMPLON",
        source_doc_id="src_2",
    )
    cand_c = CandidateEvent(
        agency="FDA",
        jurisdiction="US",
        event_type="approval",
        status="AP",
        summary="C",
        event_date=date(2024, 1, 16),
        asset_name="Examplon",
        source_doc_id="src_3",
    )
    cand_missing_date = CandidateEvent(
        agency="FDA",
        jurisdiction="US",
        event_type="approval",
        status="AP",
        summary="D",
        source_doc_id="src_4",
    )

    known: dict[str, str] = {}

    def resolver(name: str | None) -> str | None:
        resolved = resolve_asset(name, known_assets=known)
        if resolved is None:
            return None
        canonical, key = resolved
        known[key] = canonical
        return key

    grouped = dedupe_events(
        [
            ("src_1", cand_a),
            ("src_2", cand_b),
            ("src_3", cand_c),
            ("src_4", cand_missing_date),
        ],
        asset_key_resolver=resolver,
    )
    keys = list(grouped.keys())
    assert len(keys) == 2  # cand_missing_date is dropped
    # The same date+asset collapses A and B onto one key.
    same_key = event_key(
        agency="FDA",
        jurisdiction="US",
        event_type="approval",
        event_date=date(2024, 1, 15),
        asset_key=resolver("Examplon"),
    )
    assert len(grouped[same_key]) == 2
