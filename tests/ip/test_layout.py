from __future__ import annotations

from medfuel.ip.models import (
    FrameworkScores,
    IPConfidence,
    IPFinding,
    IPVerificationState,
)
from medfuel.ip.render.layout import plan_ip_layout


def _finding(fid: str, category: str, score: float = 80.0) -> IPFinding:
    return IPFinding(
        finding_id=fid,
        family_id=f"fam_{fid}",
        category=category,  # type: ignore[arg-type]
        text=f"finding {fid}",
        verification_state=IPVerificationState.VERIFIED,
        confidence=IPConfidence.HIGH,
        signal_score=score,
        framework_scores=FrameworkScores(),
        source_doc_ids=[],
        citation_numbers=[],
    )


def test_layout_default_five_pages_when_no_overflow():
    findings = [
        _finding("e1", "executive"),
        _finding("p1", "portfolio"),
        _finding("cm1", "claims_moat"),
        _finding("cc1", "commercial_competitive"),
        _finding("r1", "risk_fto"),
    ]
    layout = plan_ip_layout(findings=findings, requested_pages=5)
    assert layout.pages_rendered == 5
    assert layout.adaptive_expansion_triggered is False
    assert {s.slug for s in layout.sections} == {
        "ip_executive",
        "ip_portfolio",
        "ip_claims_moat",
        "ip_commercial_competitive",
        "ip_risk_fto",
    }


def test_layout_expands_when_many_high_signal_findings_omitted():
    findings = []
    for i in range(30):
        findings.append(_finding(f"p{i}", "portfolio", score=85))
    layout = plan_ip_layout(findings=findings, requested_pages=5, soft_max_pages=7, hard_max_pages=8)
    assert layout.adaptive_expansion_triggered is True
    assert 5 < layout.pages_rendered <= 8
    assert any("expanded" in r for r in layout.expansion_reasons)


def test_layout_respects_hard_cap():
    findings = [_finding(f"r{i}", "risk_fto", score=90) for i in range(50)]
    layout = plan_ip_layout(findings=findings, requested_pages=5, hard_max_pages=8)
    assert layout.pages_rendered <= 8
