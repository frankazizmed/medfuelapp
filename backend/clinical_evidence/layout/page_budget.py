"""Adaptive 6→10 page expansion engine (spec sections 12 + 13).

Inputs: ranked findings + per-page-role finding allocation function.
Output: number of pages to render (between default_page_target and
max_page_target) and the omitted high-signal fraction at that count.
"""

from __future__ import annotations

import logging

from clinical_evidence.config import get_settings
from clinical_evidence.schemas import ClinicalFinding, FindingType, RiskFlag, SignalScores

log = logging.getLogger(__name__)


# Rough capacity for each page in "finding slots" — keeps the calc auditable.
_PAGE_CAPACITY: dict[int, int] = {
    1: 6,   # exec summary
    2: 6,   # trial architecture
    3: 10,  # efficacy table
    4: 12,  # safety heatmap
    5: 6,   # interpretation
    6: 8,   # risks + citations
    7: 6,   # comparative
    8: 6,   # subgroup
    9: 6,   # durability
    10: 6,  # multi-indication
}


def _composite(f: ClinicalFinding) -> float:
    s = f.scores if isinstance(f.scores, SignalScores) else SignalScores(**f.scores)
    return s.composite()


def _critical_safety_omitted(findings: list[ClinicalFinding], rendered: list[ClinicalFinding]) -> bool:
    rendered_ids = {f.finding_id for f in rendered}
    for f in findings:
        s = f.scores if isinstance(f.scores, SignalScores) else SignalScores(**f.scores)
        if s.safety_concern >= 0.7 and f.finding_id not in rendered_ids:
            return True
    return False


def _registrational_unfit(findings: list[ClinicalFinding], rendered: list[ClinicalFinding]) -> bool:
    """True if more than one regulatory/late-stage finding didn't make it."""
    rendered_ids = {f.finding_id for f in rendered}
    omitted_late_stage = [
        f
        for f in findings
        if f.finding_id not in rendered_ids
        and any(rf == RiskFlag.endpoint_mismatch.value or rf == RiskFlag.endpoint_mismatch for rf in f.risk_flags) is False
        and (
            f.finding_type in (FindingType.regulatory.value, FindingType.regulatory)
            or _composite(f) > 0.65
        )
    ]
    return len(omitted_late_stage) >= 2


def decide(
    findings: list[ClinicalFinding],
    *,
    per_page_findings,
) -> tuple[int, float]:
    """Return (page_count, omitted_high_signal_fraction).

    per_page_findings(role_idx, findings) → list[ClinicalFinding].
    """

    settings = get_settings()
    if not findings:
        # No evidence to render — never expand past the default.
        return settings.default_page_target, 0.0
    total_mass = sum(_composite(f) for f in findings) or 1.0

    def _rendered_for(count: int) -> list[ClinicalFinding]:
        rendered: list[ClinicalFinding] = []
        seen_ids: set[str] = set()
        for idx in range(1, count + 1):
            cap = _PAGE_CAPACITY.get(idx, 6)
            for f in per_page_findings(idx, findings)[:cap]:
                if f.finding_id in seen_ids:
                    continue
                seen_ids.add(f.finding_id)
                rendered.append(f)
        return rendered

    page_count = settings.default_page_target
    while page_count <= settings.max_page_target:
        rendered = _rendered_for(page_count)
        rendered_mass = sum(_composite(f) for f in rendered)
        omitted_fraction = max(0.0, 1.0 - (rendered_mass / total_mass))
        if page_count >= settings.max_page_target:
            return page_count, round(omitted_fraction, 4)

        expand = False
        if omitted_fraction > settings.expansion_threshold:
            expand = True
        if _critical_safety_omitted(findings, rendered):
            expand = True
        if _registrational_unfit(findings, rendered):
            expand = True
        if not expand:
            return page_count, round(omitted_fraction, 4)
        page_count += 1

    rendered = _rendered_for(page_count)
    rendered_mass = sum(_composite(f) for f in rendered)
    return page_count, round(max(0.0, 1.0 - (rendered_mass / total_mass)), 4)
