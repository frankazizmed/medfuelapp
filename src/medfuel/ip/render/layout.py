"""Adaptive 5→7→8 page layout for IP reports.

Mechanical rules (per spec section 12-13):
  default: 5 pages
  soft max: 7 pages
  hard max: 8 pages

Expand only when omitted_high_signal_share > 10% or critical FTO /
litigation findings would otherwise be dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from medfuel.ip.models import IPFinding
from medfuel.ip.render.sections import (
    IP_SECTION_BUDGETS,
    IP_SECTION_THEMES,
    IPSectionBudget,
)
from medfuel.ip.score.signal import HIGH_SIGNAL_THRESHOLD


@dataclass
class IPSectionPlan:
    slug: str
    title: str
    budget: IPSectionBudget
    finding_ids: list[str] = field(default_factory=list)
    overflow_finding_ids: list[str] = field(default_factory=list)


@dataclass
class IPLayoutPlan:
    pages_requested: int
    pages_rendered: int
    soft_max_pages: int
    hard_max_pages: int
    adaptive_expansion_triggered: bool
    sections: list[IPSectionPlan]
    omitted_high_signal_share: float
    omitted_critical_count: int
    expansion_reasons: list[str] = field(default_factory=list)


def plan_ip_layout(
    *,
    findings: list[IPFinding],
    requested_pages: int = 5,
    soft_max_pages: int = 7,
    hard_max_pages: int = 8,
) -> IPLayoutPlan:
    by_category: dict[str, list[IPFinding]] = {}
    for f in findings:
        by_category.setdefault(f.category, []).append(f)
    for bucket in by_category.values():
        bucket.sort(key=lambda f: f.signal_score, reverse=True)

    high_signal_ids = {
        f.finding_id for f in findings if f.signal_score >= HIGH_SIGNAL_THRESHOLD
    }
    critical_ids = {
        f.finding_id
        for f in findings
        if f.category == "risk_fto" and f.signal_score >= 60
    }

    sections: list[IPSectionPlan] = []
    used: set[str] = set()
    for budget in IP_SECTION_BUDGETS:
        themes = IP_SECTION_THEMES[budget.slug]
        candidates: list[IPFinding] = []
        for theme in themes:
            candidates.extend(by_category.get(theme, []))
        picks: list[str] = []
        cap = 3 if budget.slug != "ip_portfolio" else 5
        for f in candidates:
            if f.finding_id in used:
                continue
            picks.append(f.finding_id)
            used.add(f.finding_id)
            if len(picks) >= cap:
                break
        sections.append(
            IPSectionPlan(
                slug=budget.slug,
                title=budget.title,
                budget=budget,
                finding_ids=picks,
            )
        )

    def _metrics(used_set: set[str]) -> tuple[float, int]:
        if not high_signal_ids:
            high_share = 0.0
        else:
            omitted_high = sum(1 for fid in high_signal_ids if fid not in used_set)
            high_share = omitted_high / max(len(high_signal_ids), 1)
        omitted_critical = sum(1 for fid in critical_ids if fid not in used_set)
        return high_share, omitted_critical

    pages_rendered = requested_pages
    high_share, omitted_critical = _metrics(used)
    expansion_reasons: list[str] = []

    # Adaptive expansion. Soft max is 7; hard max 8. Each loop adds one
    # page of overflow to whichever section has the most unused candidates.
    while pages_rendered < hard_max_pages and (
        high_share > 0.10 or omitted_critical > 0
    ):
        best_section: IPSectionPlan | None = None
        best_remaining: list[IPFinding] = []
        for s in sections:
            themes = IP_SECTION_THEMES[s.slug]
            candidates = [
                f
                for theme in themes
                for f in by_category.get(theme, [])
                if f.finding_id not in used
            ]
            if candidates and len(candidates) > len(best_remaining):
                best_section = s
                best_remaining = candidates
        if best_section is None:
            break
        added = [f.finding_id for f in best_remaining[:3]]
        if not added:
            break
        best_section.overflow_finding_ids.extend(added)
        used.update(added)
        pages_rendered += 1
        reason = (
            f"expanded to surface {len(added)} omitted finding(s) into "
            f"'{best_section.slug}' (omitted_high_signal_share={high_share:.2f}, "
            f"omitted_critical={omitted_critical})"
        )
        expansion_reasons.append(reason)
        high_share, omitted_critical = _metrics(used)
        if pages_rendered >= soft_max_pages and (
            high_share <= 0.10 and omitted_critical == 0
        ):
            break

    return IPLayoutPlan(
        pages_requested=requested_pages,
        pages_rendered=pages_rendered,
        soft_max_pages=soft_max_pages,
        hard_max_pages=hard_max_pages,
        adaptive_expansion_triggered=pages_rendered > requested_pages,
        sections=sections,
        omitted_high_signal_share=round(high_share, 4),
        omitted_critical_count=omitted_critical,
        expansion_reasons=expansion_reasons,
    )
