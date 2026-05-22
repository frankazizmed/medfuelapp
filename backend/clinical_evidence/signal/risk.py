"""Aggregate per-finding risks into section-level risk callouts."""

from __future__ import annotations

from collections import Counter

from clinical_evidence.schemas import ClinicalFinding, RiskFlag


_RISK_NARRATIVES = {
    RiskFlag.underpowered: "Underpowered datasets",
    RiskFlag.weak_comparator: "Weak or non-randomized comparator",
    RiskFlag.open_label: "Open-label design",
    RiskFlag.surrogate_endpoint: "Reliance on surrogate endpoints",
    RiskFlag.high_dropout: "High dropout rate",
    RiskFlag.confounding: "Potential confounding",
    RiskFlag.subgroup_dependence: "Subgroup-dependent signal",
    RiskFlag.single_site: "Single-site enrollment",
    RiskFlag.enrollment_risk: "Enrollment risk",
    RiskFlag.safety_signal: "Safety signal",
    RiskFlag.durability_concern: "Limited durability follow-up",
    RiskFlag.statistical_fragility: "Statistical fragility (p just below 0.05)",
    RiskFlag.endpoint_mismatch: "Endpoint mismatch with regulatory expectations",
    RiskFlag.publication_gap: "Unpublished pivotal data",
    RiskFlag.inconsistent: "Inconsistent findings across sources",
}


def summarize(findings: list[ClinicalFinding]) -> list[tuple[str, int]]:
    """Return ranked (risk label, count) pairs for the risks page."""

    counter: Counter[str] = Counter()
    for f in findings:
        for r in f.risk_flags:
            key = r if isinstance(r, str) else r.value
            label = _RISK_NARRATIVES.get(RiskFlag(key)) if key in {v.value for v in RiskFlag} else None
            if label:
                counter[label] += 1
    return counter.most_common()
