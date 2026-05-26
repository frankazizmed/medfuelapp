from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SectionBudget:
    slug: str
    title: str
    word_min: int
    word_max: int
    objective: str
    visuals: str


# Six-page institutional baseline from the design doc. Word budgets sum to a
# tight ~1,360-1,780 narrative band; the point is decision density, not bulk.
SECTION_BUDGETS: tuple[SectionBudget, ...] = (
    SectionBudget(
        slug="executive_summary",
        title="Executive summary",
        word_min=260,
        word_max=320,
        objective="Regulatory posture at a glance",
        visuals="1 scorecard + 1 callout",
    ),
    SectionBudget(
        slug="pathway_matrix",
        title="Pathway matrix",
        word_min=180,
        word_max=240,
        objective="Asset/jurisdiction view",
        visuals="1 matrix table",
    ),
    SectionBudget(
        slug="timeline",
        title="Timeline",
        word_min=160,
        word_max=220,
        objective="Chronology of major events",
        visuals="1 horizontal timeline",
    ),
    SectionBudget(
        slug="trials_and_evidence",
        title="Trials and evidence",
        word_min=280,
        word_max=360,
        objective="Link trials to regulatory narrative",
        visuals="1 trial/evidence table",
    ),
    SectionBudget(
        slug="safety_quality_compliance",
        title="Safety, quality, compliance",
        word_min=260,
        word_max=340,
        objective="Downside and diligence risks",
        visuals="1 heatmap or issue table",
    ),
    SectionBudget(
        slug="implications_and_watchlist",
        title="Implications and watchlist",
        word_min=220,
        word_max=300,
        objective="Investor meaning",
        visuals="1 catalyst/watchlist box",
    ),
)


SECTION_THEMES: dict[str, tuple[str, ...]] = {
    "executive_summary": (),  # synthesizes top items across all themes
    "pathway_matrix": ("approval", "clearance", "designation"),
    "timeline": (
        "approval",
        "clearance",
        "designation",
        "clinical_hold",
        "warning",
        "inspection",
        "label_change",
        "trial_update",
        "offering_or_filing",
        "manufacturing_issue",
        "patent_event",
    ),
    "trials_and_evidence": ("trial_update", "clinical_hold"),
    "safety_quality_compliance": (
        "warning",
        "inspection",
        "label_change",
        "manufacturing_issue",
        "clinical_hold",
    ),
    "implications_and_watchlist": (),  # forward-looking synthesis
}
