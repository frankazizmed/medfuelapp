from clinical_evidence.layout.page_budget import decide
from clinical_evidence.narrative.generator import _findings_for_page
from clinical_evidence.schemas import (
    ClinicalFinding,
    EndpointType,
    FindingType,
    SignalScores,
    VerificationStatus,
)
from clinical_evidence.signal.scorer import score_findings
from clinical_evidence.tests.fixtures import sample_findings, sample_trials


def _heavy_finding(idx: int) -> ClinicalFinding:
    """Generate a high-signal finding that earns its own page slot."""
    return ClinicalFinding(
        finding_id=f"f-heavy-{idx}",
        company_id="co-acme",
        trial_id="tr-NCT01",
        source_doc_id=f"pm-doc-{idx}",
        finding_type=FindingType.efficacy,
        endpoint=f"hard endpoint {idx}",
        endpoint_type=EndpointType.hard,
        description=f"High signal finding {idx}",
        verification_status=VerificationStatus.VERIFIED,
        scores=SignalScores(
            evidence_strength=0.9,
            endpoint_quality=0.9,
            statistical_robustness=0.9,
            physician_relevance=0.9,
            commercialization_relevance=0.9,
            differentiation=0.7,
            safety_concern=0.05,
            regulatory_relevance=0.9,
            durability=0.7,
        ),
        risk_flags=[],
    )


def test_default_six_pages_for_modest_evidence():
    findings = score_findings(sample_findings(), trials=sample_trials())
    page_count, omitted = decide(findings, per_page_findings=_findings_for_page)
    assert 6 <= page_count <= 10
    assert page_count == 6
    assert 0.0 <= omitted <= 1.0


def test_expansion_when_many_high_signal_findings():
    findings = score_findings(sample_findings(), trials=sample_trials())
    # 30 extra high-signal findings spread across many trials → must expand.
    findings = findings + [_heavy_finding(i) for i in range(30)]
    page_count, omitted = decide(findings, per_page_findings=_findings_for_page)
    assert page_count > 6
    assert page_count <= 10


def test_hard_stop_at_max_page_target():
    findings = score_findings(sample_findings(), trials=sample_trials())
    findings = findings + [_heavy_finding(i) for i in range(500)]
    page_count, _ = decide(findings, per_page_findings=_findings_for_page)
    assert page_count == 10
