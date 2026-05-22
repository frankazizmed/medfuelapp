from clinical_evidence.schemas import EndpointType, FindingType, RiskFlag, SignalScores
from clinical_evidence.signal.scorer import score_findings
from clinical_evidence.tests.fixtures import sample_findings, sample_trials


def test_hard_endpoint_outranks_subgroup():
    findings = score_findings(sample_findings(), trials=sample_trials())
    by_id = {f.finding_id: f for f in findings}
    efficacy = by_id["f-eff-1"]
    subgroup = by_id["f-subgroup-thin"]
    assert efficacy.scores.composite() > subgroup.scores.composite()


def test_late_phase_rct_lifts_evidence_strength():
    findings = score_findings(sample_findings(), trials=sample_trials())
    efficacy = next(f for f in findings if f.finding_id == "f-eff-1")
    assert efficacy.scores.evidence_strength >= 0.7


def test_significant_p_value_lifts_statistical_robustness():
    findings = score_findings(sample_findings(), trials=sample_trials())
    efficacy = next(f for f in findings if f.finding_id == "f-eff-1")
    assert efficacy.scores.statistical_robustness >= 0.8


def test_subgroup_underpowered_gets_risk_flags():
    findings = score_findings(sample_findings(), trials=sample_trials())
    subgroup = next(f for f in findings if f.finding_id == "f-subgroup-thin")
    assert RiskFlag.underpowered.value in [
        (r if isinstance(r, str) else r.value) for r in subgroup.risk_flags
    ]
    assert RiskFlag.subgroup_dependence.value in [
        (r if isinstance(r, str) else r.value) for r in subgroup.risk_flags
    ]


def test_endpoint_classification_promotes_hard():
    findings = score_findings(sample_findings(), trials=sample_trials())
    efficacy = next(f for f in findings if f.finding_id == "f-eff-1")
    assert (
        efficacy.endpoint_type == EndpointType.hard.value
        or efficacy.endpoint_type == EndpointType.hard
    )
