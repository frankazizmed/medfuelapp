"""Aggressively remove low-signal findings (Sections 8 + 15).

A finding survives only if it materially changes interpretation, adoption,
safety, regulatory progress, or commercial potential.
"""

from __future__ import annotations

import logging
import re

from clinical_evidence.schemas import ClinicalFinding, FindingType, SignalScores

log = logging.getLogger(__name__)


_FLUFF_PATTERNS = (
    re.compile(r"\bpromising\b", re.IGNORECASE),
    re.compile(r"\bpotentially transformative\b", re.IGNORECASE),
    re.compile(r"\bbest[- ]in[- ]class\b", re.IGNORECASE),
    re.compile(r"\brevolutionary\b", re.IGNORECASE),
    re.compile(r"\bgame[- ]changing\b", re.IGNORECASE),
    re.compile(r"\bgroundbreaking\b", re.IGNORECASE),
    re.compile(r"\bparadigm[- ]shifting\b", re.IGNORECASE),
)

_MOA_PATTERNS = (
    re.compile(r"\bmechanism of action\b", re.IGNORECASE),
    re.compile(r"\bMOA\b"),
    re.compile(r"\bbinds to .{1,40} receptor\b", re.IGNORECASE),
)

_DISEASE_BACKGROUND_PATTERNS = (
    re.compile(
        r"\b(disease|condition|disorder)\s+affects?\s+[0-9.,]+\s*(?:million|billion|thousand)?\s+people\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bglobally affecting\b", re.IGNORECASE),
    re.compile(r"\baffects?\s+[0-9.,]+\s*(?:million|billion|thousand)\s+people\b", re.IGNORECASE),
)


def contains_fluff(text: str) -> bool:
    return any(p.search(text) for p in _FLUFF_PATTERNS)


def is_generic_moa(text: str) -> bool:
    return any(p.search(text) for p in _MOA_PATTERNS)


def is_disease_background(text: str) -> bool:
    return any(p.search(text) for p in _DISEASE_BACKGROUND_PATTERNS)


def _materially_significant(finding: ClinicalFinding) -> bool:
    s: SignalScores = finding.scores if isinstance(finding.scores, SignalScores) else SignalScores(**finding.scores)
    composite = s.composite()
    if composite >= 0.45:
        return True
    if s.safety_concern >= 0.6:
        return True
    if s.regulatory_relevance >= 0.7:
        return True
    if s.evidence_strength >= 0.7 and s.endpoint_quality >= 0.6:
        return True
    return False


def filter_noise(findings: list[ClinicalFinding]) -> list[ClinicalFinding]:
    out: list[ClinicalFinding] = []
    dropped_fluff = 0
    dropped_moa = 0
    dropped_thin = 0
    dropped_subgroup = 0
    for f in findings:
        text = f.description or ""
        if contains_fluff(text):
            dropped_fluff += 1
            continue
        if is_generic_moa(text) and f.finding_type in (
            FindingType.pharmacology.value,
            FindingType.pharmacology,
        ):
            dropped_moa += 1
            continue
        if is_disease_background(text):
            dropped_thin += 1
            continue
        if f.finding_type in (FindingType.subgroup.value, FindingType.subgroup) and not _materially_significant(f):
            dropped_subgroup += 1
            continue
        if not _materially_significant(f):
            dropped_thin += 1
            continue
        out.append(f)
    log.info(
        "Filter: kept %d / dropped fluff=%d moa=%d thin=%d subgroup=%d",
        len(out),
        dropped_fluff,
        dropped_moa,
        dropped_thin,
        dropped_subgroup,
    )
    return out
