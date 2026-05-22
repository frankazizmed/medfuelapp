"""Five-page IP report skeleton.

Page architecture follows the design doc:
  1. Executive summary
  2. Portfolio architecture
  3. Claims + moat analysis
  4. Commercial + competitive implications
  5. Key risks + FTO

Each section carries:
  - a tight word budget (max strategic-insight per page);
  - an objective sentence the narrator uses to anchor tone;
  - a visual the layout planner expects to surface.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IPSectionBudget:
    slug: str
    title: str
    word_min: int
    word_max: int
    objective: str
    visuals: str


IP_SECTION_BUDGETS: tuple[IPSectionBudget, ...] = (
    IPSectionBudget(
        slug="ip_executive",
        title="IP Executive Summary",
        word_min=220,
        word_max=300,
        objective="Defensibility posture, strongest assets, key risks, exclusivity stance",
        visuals="1 scorecard + 1 risk callout",
    ),
    IPSectionBudget(
        slug="ip_portfolio",
        title="Portfolio Architecture",
        word_min=200,
        word_max=280,
        objective="Family structure, jurisdictions, claim mix, continuation strategy",
        visuals="1 family table + 1 jurisdiction matrix",
    ),
    IPSectionBudget(
        slug="ip_claims_moat",
        title="Claim Strength and Moat",
        word_min=220,
        word_max=300,
        objective="Breadth, enforceability, design-around difficulty, differentiation",
        visuals="1 claim-breadth grid + 1 forward-citation heatmap",
    ),
    IPSectionBudget(
        slug="ip_commercial_competitive",
        title="Commercial and Competitive Implications",
        word_min=200,
        word_max=280,
        objective="Product/manufacturing coverage, competitor overlap, white space",
        visuals="1 competitor overlap matrix",
    ),
    IPSectionBudget(
        slug="ip_risk_fto",
        title="Key Risks and FTO",
        word_min=200,
        word_max=280,
        objective="Blocking risks, litigation/PTAB exposure, expiration concerns",
        visuals="1 risk heatmap + 1 exclusivity timeline",
    ),
)


# Which finding categories map onto which sections. Used by the layout planner.
IP_SECTION_THEMES: dict[str, tuple[str, ...]] = {
    "ip_executive": ("executive",),
    "ip_portfolio": ("portfolio",),
    "ip_claims_moat": ("claims_moat",),
    "ip_commercial_competitive": ("commercial_competitive",),
    "ip_risk_fto": ("risk_fto",),
}
