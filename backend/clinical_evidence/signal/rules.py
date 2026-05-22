"""Deterministic heuristics used by the signal scorer.

These rules encode what sophisticated healthcare investors actually weight.
They are intentionally explicit so the scoring is auditable and stable
across runs. Anything ambiguous is handed to the LLM judge in scorer.py.
"""

from __future__ import annotations

from clinical_evidence.schemas import (
    ClinicalFinding,
    EndpointType,
    FindingType,
    RiskFlag,
    Trial,
)


HARD_ENDPOINT_KEYWORDS = (
    "mortality",
    "overall survival",
    "cardiovascular death",
    "major adverse",
    "mace",
    "stroke",
    "myocardial infarction",
    "hospitalization",
    "all-cause death",
    "progression-free survival",  # accepted as quasi-hard in oncology
    "amputation",
    "dialysis",
    "esrd",
    "transplant",
    "fracture",
)

SURROGATE_ENDPOINT_KEYWORDS = (
    "ldl",
    "hdl",
    "hba1c",
    "biomarker",
    "blood pressure",
    "qol",
    "quality of life",
    "imaging",
    "tumor response",
    "objective response rate",
    "pro",
    "patient reported outcome",
)

DURABLE_HORIZON_MONTHS = 12


def classify_endpoint(label: str | None) -> EndpointType:
    if not label:
        return EndpointType.unknown
    lower = label.lower()
    if any(k in lower for k in HARD_ENDPOINT_KEYWORDS):
        return EndpointType.hard
    if any(k in lower for k in SURROGATE_ENDPOINT_KEYWORDS):
        return EndpointType.surrogate
    if " and " in lower or " or " in lower or "composite" in lower:
        return EndpointType.composite
    return EndpointType.unknown


def evidence_strength(finding: ClinicalFinding, trial: Trial | None) -> float:
    """0..1 — how strong is the evidence behind this claim?"""
    score = 0.3
    if trial:
        if trial.randomized:
            score += 0.2
        if trial.blinded:
            score += 0.1
        if trial.placebo_controlled:
            score += 0.1
        if trial.phase in ("phase3", "phase4"):
            score += 0.15
        elif trial.phase in ("phase2", "phase2_3"):
            score += 0.08
    n = finding.result.n if finding.result else None
    if n:
        if n >= 1000:
            score += 0.15
        elif n >= 300:
            score += 0.08
        elif n < 50:
            score -= 0.1
    return max(0.0, min(1.0, score))


def endpoint_quality(finding: ClinicalFinding) -> float:
    et = finding.endpoint_type or classify_endpoint(finding.endpoint)
    if et == EndpointType.hard:
        return 0.9
    if et == EndpointType.composite:
        return 0.65
    if et == EndpointType.surrogate:
        return 0.4
    return 0.3


def statistical_robustness(finding: ClinicalFinding) -> float:
    if not finding.result:
        return 0.3
    p = finding.result.p_value
    n = finding.result.n
    score = 0.3
    if p is not None:
        if p < 0.001:
            score = 0.95
        elif p < 0.01:
            score = 0.85
        elif p < 0.05:
            score = 0.7
        elif p < 0.1:
            score = 0.4
        else:
            score = 0.2
    if n:
        if n >= 1000:
            score += 0.05
        elif n < 50:
            score -= 0.15
    return max(0.0, min(1.0, score))


def physician_relevance(finding: ClinicalFinding) -> float:
    """Heuristic — efficacy on hard endpoints + clean safety scores well."""
    if finding.finding_type == FindingType.efficacy.value or finding.finding_type == FindingType.efficacy:
        base = 0.55
        if endpoint_quality(finding) > 0.7:
            base += 0.2
        return min(1.0, base)
    if finding.finding_type in (FindingType.safety.value, FindingType.safety):
        return 0.5
    if finding.finding_type in (FindingType.durability.value, FindingType.durability):
        return 0.55
    return 0.3


def commercialization_relevance(finding: ClinicalFinding) -> float:
    base = 0.3
    if finding.finding_type in (FindingType.efficacy.value, FindingType.efficacy):
        base = 0.55
    if endpoint_quality(finding) > 0.7:
        base += 0.15
    if finding.result and finding.result.p_value is not None and finding.result.p_value < 0.05:
        base += 0.1
    return min(1.0, base)


def differentiation(finding: ClinicalFinding) -> float:
    """Default until LLM judge fills in. Higher if comparator beaten."""
    if finding.finding_type in (FindingType.comparator.value, FindingType.comparator):
        return 0.7
    return 0.35


def safety_concern(finding: ClinicalFinding) -> float:
    """Higher = more concerning."""
    if finding.finding_type not in (FindingType.safety.value, FindingType.safety):
        return 0.05
    text = (finding.description or "").lower()
    score = 0.4
    if any(k in text for k in ("death", "fatal", "serious adverse", "sae")):
        score = 0.85
    elif any(k in text for k in ("discontinuation", "withdraw")):
        score = 0.55
    return min(1.0, score)


def regulatory_relevance(finding: ClinicalFinding, trial: Trial | None) -> float:
    base = 0.3
    if trial and trial.phase in ("phase3", "phase2_3", "phase4"):
        base += 0.3
    if finding.finding_type in (FindingType.regulatory.value, FindingType.regulatory):
        base += 0.3
    if endpoint_quality(finding) > 0.7:
        base += 0.1
    return min(1.0, base)


def durability(finding: ClinicalFinding) -> float:
    months = finding.follow_up_months
    if months is None:
        return 0.3
    if months >= 24:
        return 0.9
    if months >= 12:
        return 0.7
    if months >= 6:
        return 0.5
    return 0.3


def detect_risks(finding: ClinicalFinding, trial: Trial | None) -> list[RiskFlag]:
    flags: list[RiskFlag] = []
    n = finding.result.n if finding.result else None
    if n is not None and n < 50:
        flags.append(RiskFlag.underpowered)
    if trial:
        if trial.randomized is False:
            flags.append(RiskFlag.weak_comparator)
        if trial.blinded is False:
            flags.append(RiskFlag.open_label)
    if finding.endpoint_type == EndpointType.surrogate.value or finding.endpoint_type == EndpointType.surrogate:
        flags.append(RiskFlag.surrogate_endpoint)
    if finding.finding_type in (FindingType.subgroup.value, FindingType.subgroup):
        flags.append(RiskFlag.subgroup_dependence)
    p = finding.result.p_value if finding.result else None
    if p is not None and 0.04 < p < 0.05:
        flags.append(RiskFlag.statistical_fragility)
    if finding.follow_up_months is not None and finding.follow_up_months < 6:
        flags.append(RiskFlag.durability_concern)
    if safety_concern(finding) > 0.7:
        flags.append(RiskFlag.safety_signal)
    return flags
