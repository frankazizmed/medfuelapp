"""Per-finding confidence score (used downstream by citations + signal)."""

from __future__ import annotations

from clinical_evidence.schemas import ClinicalFinding, SourceKind, VerificationStatus

_PRIMARY_SOURCES = {
    SourceKind.clinicaltrials,
    SourceKind.pubmed,
    SourceKind.fda,
    SourceKind.ema,
    SourceKind.preprint,
}


def confidence_for(finding: ClinicalFinding, source: SourceKind) -> float:
    base = 0.4
    if source in _PRIMARY_SOURCES:
        base = 0.7
    if source == SourceKind.press_release:
        base = 0.35

    status = finding.verification_status
    if status == VerificationStatus.VERIFIED.value or status == VerificationStatus.VERIFIED:
        base += 0.2
    if status == VerificationStatus.INFERRED.value or status == VerificationStatus.INFERRED:
        base -= 0.15

    if finding.result and finding.result.p_value is not None and finding.result.p_value < 0.05:
        base += 0.05
    if finding.result and finding.result.n and finding.result.n >= 500:
        base += 0.05

    return max(0.0, min(1.0, round(base, 3)))
