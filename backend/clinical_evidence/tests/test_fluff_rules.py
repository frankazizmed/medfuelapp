from clinical_evidence.signal.filter import (
    contains_fluff,
    filter_noise,
    is_disease_background,
    is_generic_moa,
)
from clinical_evidence.signal.scorer import score_findings
from clinical_evidence.tests.fixtures import sample_findings, sample_trials


def test_promising_is_flagged():
    assert contains_fluff("ACME-101 is a promising therapy")
    assert contains_fluff("potentially transformative outcome")
    assert not contains_fluff("HR 0.78, p<0.001")


def test_moa_pattern_flagged():
    assert is_generic_moa("the mechanism of action involves binding")


def test_disease_background_flagged():
    assert is_disease_background("This condition affects 30 million people globally")


def test_filter_drops_fluff_finding():
    findings = score_findings(sample_findings(), trials=sample_trials())
    kept = filter_noise(findings)
    kept_ids = {f.finding_id for f in kept}
    assert "f-fluff" not in kept_ids
    assert "f-eff-1" in kept_ids


def test_filter_drops_thin_subgroup():
    findings = score_findings(sample_findings(), trials=sample_trials())
    kept = filter_noise(findings)
    kept_ids = {f.finding_id for f in kept}
    assert "f-subgroup-thin" not in kept_ids
