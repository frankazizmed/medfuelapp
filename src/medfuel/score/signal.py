from __future__ import annotations

from medfuel.models import RegulatoryEvent

# Weights from the design's signal formula. Keep these in one place so
# auditing changes to the rubric stays a single-file diff.
SIGNAL_WEIGHTS: dict[str, float] = {
    "relevance": 0.30,
    "evidence_strength": 0.30,
    "uniqueness": 0.15,
    "investor_importance": 0.25,
}

# Event types that the design explicitly calls out as "critical items" — they
# must surface in the six-page baseline once verified.
_CRITICAL_EVENT_TYPES: set[str] = {
    "approval",
    "clinical_hold",
    "warning",
    "inspection",
    "label_change",
    "manufacturing_issue",
}


def critical_event_types() -> set[str]:
    return set(_CRITICAL_EVENT_TYPES)


def is_critical(event: RegulatoryEvent) -> bool:
    return event.event_type in _CRITICAL_EVENT_TYPES


def _relevance(event: RegulatoryEvent) -> float:
    # Regulatory consequence is high for any non-patent regulatory event;
    # patent events score lower unless investor importance lifts them.
    if event.event_type == "patent_event":
        return 0.5
    return 0.9 if event.event_type in _CRITICAL_EVENT_TYPES else 0.7


def _uniqueness(event: RegulatoryEvent) -> float:
    # Single-source events are more "unique" by default but get penalized by
    # weaker corroboration. Two corroborating sources balance to ~0.6, three+
    # land near 0.8. The cap protects against echo-chamber inflation.
    n = max(len(event.source_doc_ids), 1)
    return min(0.4 + 0.2 * n, 0.9)


def compute_signal_score(event: RegulatoryEvent) -> float:
    relevance = _relevance(event)
    uniqueness = _uniqueness(event)
    evidence = event.evidence_strength / 5.0
    investor = event.investor_importance / 5.0

    raw = (
        SIGNAL_WEIGHTS["relevance"] * relevance
        + SIGNAL_WEIGHTS["evidence_strength"] * evidence
        + SIGNAL_WEIGHTS["uniqueness"] * uniqueness
        + SIGNAL_WEIGHTS["investor_importance"] * investor
    )
    return round(100.0 * raw, 2)
