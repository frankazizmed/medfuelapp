from __future__ import annotations

from dataclasses import dataclass, field

from medfuel.models import RegulatoryEvent, VerifiedClaim
from medfuel.render.sections import SECTION_BUDGETS, SECTION_THEMES, SectionBudget
from medfuel.score.signal import is_critical

# Signal-score thresholds from the design doc. Kept module-level so a future
# scoring tweak only requires changing one constant.
SCORE_MUST_INCLUDE = 85.0
SCORE_PREFER = 75.0
SCORE_TABLE_ONLY = 55.0

HIGH_SIGNAL_THRESHOLD = 75.0


@dataclass
class SectionPlan:
    slug: str
    title: str
    budget: SectionBudget
    claim_ids: list[str] = field(default_factory=list)
    overflow_claim_ids: list[str] = field(default_factory=list)


@dataclass
class LayoutPlan:
    pages_requested: int
    pages_rendered: int
    max_pages: int
    adaptive_expansion_triggered: bool
    sections: list[SectionPlan]
    omitted_critical_count: int
    omitted_high_signal_share: float
    expansion_reasons: list[str] = field(default_factory=list)


def _claims_by_event(
    events: list[RegulatoryEvent],
    claims: list[VerifiedClaim],
) -> dict[str, tuple[RegulatoryEvent, VerifiedClaim]]:
    by_event = {e.event_id: e for e in events}
    out: dict[str, tuple[RegulatoryEvent, VerifiedClaim]] = {}
    for claim in claims:
        event = by_event.get(claim.event_id)
        if event is None:
            continue
        out[claim.claim_id] = (event, claim)
    return out


def _claims_for_section(
    section: SectionBudget,
    pool: dict[str, tuple[RegulatoryEvent, VerifiedClaim]],
) -> list[str]:
    themes = SECTION_THEMES.get(section.slug, ())
    candidates = list(pool.items())
    if themes:
        candidates = [
            (cid, (e, c)) for cid, (e, c) in candidates if e.event_type in themes
        ]
    # Sort by signal score desc, then by date desc so the most recent ties win.
    candidates.sort(
        key=lambda kv: (kv[1][1].signal_score, kv[1][0].event_date),
        reverse=True,
    )
    return [cid for cid, _ in candidates]


def plan_layout(
    *,
    events: list[RegulatoryEvent],
    claims: list[VerifiedClaim],
    requested_pages: int = 4,
    max_pages: int = 8,
) -> LayoutPlan:
    """Mechanical pagination per the design's expansion rules.

    Builds the six baseline sections, fills each with the highest-signal
    claims, and then expands one page at a time only when the design's
    omission triggers are tripped.
    """
    pool = _claims_by_event(events, claims)
    high_signal_pool = [
        cid for cid, (_, c) in pool.items() if c.signal_score >= HIGH_SIGNAL_THRESHOLD
    ]
    critical_pool = [
        cid for cid, (e, _) in pool.items() if is_critical(e)
    ]

    sections: list[SectionPlan] = []
    used_claim_ids: set[str] = set()
    for budget in SECTION_BUDGETS:
        ranked = _claims_for_section(budget, pool)
        # Top three high-signal claims per themed section, top six for the
        # executive summary / implications synthesis sections.
        cap = 6 if not SECTION_THEMES.get(budget.slug) else 3
        picks = [cid for cid in ranked if cid not in used_claim_ids][:cap]
        for cid in picks:
            used_claim_ids.add(cid)
        sections.append(
            SectionPlan(
                slug=budget.slug,
                title=budget.title,
                budget=budget,
                claim_ids=picks,
            )
        )

    pages_rendered = requested_pages
    expansion_reasons: list[str] = []

    def _omitted_metrics(used: set[str]) -> tuple[int, float]:
        omitted_critical = sum(1 for cid in critical_pool if cid not in used)
        if not high_signal_pool:
            return omitted_critical, 0.0
        omitted_high = sum(1 for cid in high_signal_pool if cid not in used)
        return omitted_critical, omitted_high / max(len(high_signal_pool), 1)

    omitted_critical, omitted_share = _omitted_metrics(used_claim_ids)

    # Adaptive expansion: append overflow pages keyed off the existing
    # safety/quality/compliance and trials/evidence sections, since those
    # absorb most secondary content in a diligence report.
    while pages_rendered < max_pages and (
        omitted_critical > 0 or omitted_share > 0.10
    ):
        # Identify a section whose remaining themed claims would benefit most.
        best_section: SectionPlan | None = None
        best_remaining: list[str] = []
        for s in sections:
            ranked = _claims_for_section(s.budget, pool)
            remaining = [cid for cid in ranked if cid not in used_claim_ids]
            if remaining and (
                best_section is None or len(remaining) > len(best_remaining)
            ):
                best_section = s
                best_remaining = remaining
        if best_section is None:
            # Nothing to add even though metrics say we'd want to: stop.
            break

        added = best_remaining[:3]
        if not added:
            break
        best_section.overflow_claim_ids.extend(added)
        used_claim_ids.update(added)
        pages_rendered += 1
        if omitted_critical > 0:
            expansion_reasons.append(
                f"expanded to surface {len(added)} critical or high-signal items "
                f"into '{best_section.slug}'"
            )
        else:
            expansion_reasons.append(
                f"expanded to bring omitted high-signal share <= 10% via '{best_section.slug}'"
            )
        omitted_critical, omitted_share = _omitted_metrics(used_claim_ids)

    return LayoutPlan(
        pages_requested=requested_pages,
        pages_rendered=pages_rendered,
        max_pages=max_pages,
        adaptive_expansion_triggered=pages_rendered > requested_pages,
        sections=sections,
        omitted_critical_count=omitted_critical,
        omitted_high_signal_share=round(omitted_share, 4),
        expansion_reasons=expansion_reasons,
    )
