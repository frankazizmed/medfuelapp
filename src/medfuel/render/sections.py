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


# Four-page institutional baseline. Collapses the original six-section layout:
# pathway matrix + timeline merge into one milestone/chronology section, and
# trials + safety/quality/compliance merge into one risk section. Word budgets
# are rebalanced to keep decision density high on fewer pages.
SECTION_BUDGETS: tuple[SectionBudget, ...] = (
    SectionBudget(
        slug="executive_summary",
        title="Executive summary",
        word_min=280,
        word_max=340,
        objective="Regulatory posture at a glance",
        visuals="1 scorecard + 1 callout",
    ),
    SectionBudget(
        slug="pathway_and_timeline",
        title="Pathway and timeline",
        word_min=260,
        word_max=340,
        objective="Asset/jurisdiction view plus chronology of major events",
        visuals="1 matrix table + 1 horizontal timeline",
    ),
    SectionBudget(
        slug="trials_safety_compliance",
        title="Trials, safety and compliance",
        word_min=320,
        word_max=420,
        objective="Trial evidence linked to downside and diligence risks",
        visuals="1 trial/evidence table + 1 issue heatmap",
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


# Themed sections partition the eleven event types between the two middle
# sections; the synthesis sections (empty tuple) pull the highest-signal
# claims across all themes.
SECTION_THEMES: dict[str, tuple[str, ...]] = {
    "executive_summary": (),  # synthesizes top items across all themes
    "pathway_and_timeline": (
        "approval",
        "clearance",
        "designation",
        "offering_or_filing",
        "patent_event",
    ),
    "trials_safety_compliance": (
        "trial_update",
        "clinical_hold",
        "warning",
        "inspection",
        "label_change",
        "manufacturing_issue",
    ),
    "implications_and_watchlist": (),  # forward-looking synthesis
}
