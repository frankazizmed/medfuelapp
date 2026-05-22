"""IP Intelligence Engine.

Institutional IP diligence module: source discovery, structured
extraction, verification, six-framework scoring, signal/noise filter,
adaptive 5-page narrative.

Not a patent listing engine. Not a legal memo generator.
"""

from medfuel.ip.models import (
    AssignmentEvent,
    ClaimBreadth,
    ClaimType,
    FilingKind,
    FrameworkScores,
    IPConfidence,
    IPDiscoveryResult,
    IPFinding,
    IPReportPlan,
    IPSourceType,
    IPVerificationState,
    LegalStatus,
    LitigationRecord,
    PatentClaim,
    PatentFamily,
    PatentRecord,
    PTABProceeding,
)

__all__ = [
    "AssignmentEvent",
    "ClaimBreadth",
    "ClaimType",
    "FilingKind",
    "FrameworkScores",
    "IPConfidence",
    "IPDiscoveryResult",
    "IPFinding",
    "IPReportPlan",
    "IPSourceType",
    "IPVerificationState",
    "LegalStatus",
    "LitigationRecord",
    "PTABProceeding",
    "PatentClaim",
    "PatentFamily",
    "PatentRecord",
]
