from __future__ import annotations

from collections.abc import Iterable

from medfuel.models import CandidateEvent


def event_key(
    *,
    agency: str,
    jurisdiction: str,
    event_type: str,
    event_date,
    asset_key: str | None,
) -> str:
    """Stable, semantic key for event-level dedupe.

    Two candidates collapse onto the same key when their (agency, jurisdiction,
    type, date, asset) tuple matches. This is intentionally strict: borderline
    cases stay as separate events and surface for verifier-level review.
    """
    asset = asset_key or "_any_"
    return f"{agency}|{jurisdiction}|{event_type}|{event_date.isoformat()}|{asset}"


def dedupe_events(
    candidates: Iterable[tuple[str, CandidateEvent]],
    *,
    asset_key_resolver,
) -> dict[str, list[tuple[str, CandidateEvent]]]:
    """Group (key -> list of candidates) so the verifier can merge per key.

    Each candidate is paired with its asset_key when present, then bucketed
    under `event_key`. Candidates without a usable event_date are dropped here
    and become the verifier's "rejected for missing date" signal.
    """
    grouped: dict[str, list[tuple[str, CandidateEvent]]] = {}
    for source_doc_id, cand in candidates:
        if cand.event_date is None:
            continue
        asset_key = asset_key_resolver(cand.asset_name)
        key = event_key(
            agency=cand.agency,
            jurisdiction=cand.jurisdiction,
            event_type=cand.event_type,
            event_date=cand.event_date,
            asset_key=asset_key,
        )
        grouped.setdefault(key, []).append((source_doc_id, cand))
    return grouped
