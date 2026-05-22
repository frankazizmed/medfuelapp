"""Pydantic models for the IP Intelligence Engine.

These are the structured shapes that flow between the IP discovery
adapters, the extraction layer, the verification layer, the six
framework scorers, the signal/noise engine, and the narrative renderer.

The naming and conventions deliberately mirror the regulatory pipeline
(see medfuel.models.extraction) so investors get a consistent surface
across diligence sections.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IPSourceType(str, Enum):
    USPTO = "uspto"
    PATENTSVIEW = "patentsview"
    GOOGLE_PATENTS = "google_patents"
    EPO = "epo"
    WIPO = "wipo"
    USPTO_ASSIGNMENT = "uspto_assignment"
    PTAB = "ptab"
    LITIGATION = "litigation"
    SEC_IP = "sec_ip"
    COMPANY_IP = "company_ip"


# Authority ranking for citations. Tribunal/registry records outrank
# secondary sources; company-provided assertions sit at the bottom.
IP_OFFICIAL_RANK: dict[IPSourceType, int] = {
    IPSourceType.USPTO: 1,
    IPSourceType.EPO: 1,
    IPSourceType.WIPO: 1,
    IPSourceType.USPTO_ASSIGNMENT: 1,
    IPSourceType.PTAB: 1,
    IPSourceType.LITIGATION: 1,
    IPSourceType.PATENTSVIEW: 2,
    IPSourceType.GOOGLE_PATENTS: 3,
    IPSourceType.SEC_IP: 2,
    IPSourceType.COMPANY_IP: 4,
}


# --------------------------------------------------------------------------- claims


class ClaimType(str, Enum):
    COMPOSITION = "composition"
    METHOD = "method"
    DEVICE = "device"
    USE = "use"
    PROCESS = "process"
    SOFTWARE = "software"
    SYSTEM = "system"
    OTHER = "other"


class ClaimBreadth(str, Enum):
    BROAD = "broad"
    MODERATE = "moderate"
    NARROW = "narrow"


class PatentClaim(BaseModel):
    """A single claim, normalized for the signal/noise + framework engines."""

    claim_number: int
    text: str
    is_independent: bool
    claim_type: ClaimType = ClaimType.OTHER
    breadth: ClaimBreadth = ClaimBreadth.MODERATE
    depends_on: int | None = None
    word_count: int = 0
    novelty_terms: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- patents / families


class LegalStatus(str, Enum):
    PENDING = "pending"
    GRANTED = "granted"
    ABANDONED = "abandoned"
    EXPIRED = "expired"
    LAPSED = "lapsed"
    LITIGATED = "litigated"
    UNKNOWN = "unknown"


class FilingKind(str, Enum):
    UTILITY = "utility"
    PROVISIONAL = "provisional"
    CONTINUATION = "continuation"
    CONTINUATION_IN_PART = "continuation_in_part"
    DIVISIONAL = "divisional"
    REISSUE = "reissue"
    PCT = "pct"
    DESIGN = "design"
    OTHER = "other"


class PatentRecord(BaseModel):
    """A single patent or application as discovered from any source.

    `verification_state` is left as INFERRED at discovery time and is
    upgraded by the verification layer when corroborated against an
    official-rank document.
    """

    patent_id: str
    publication_number: str | None = None
    application_number: str | None = None
    title: str
    jurisdiction: str
    kind: FilingKind = FilingKind.UTILITY
    filing_date: date | None = None
    priority_date: date | None = None
    publication_date: date | None = None
    grant_date: date | None = None
    expiration_estimate: date | None = None
    legal_status: LegalStatus = LegalStatus.UNKNOWN
    assignees: list[str] = Field(default_factory=list)
    inventors: list[str] = Field(default_factory=list)
    family_id: str | None = None
    parent_publication_numbers: list[str] = Field(default_factory=list)
    cpc_codes: list[str] = Field(default_factory=list)
    forward_citations: int = 0
    backward_citations: int = 0
    independent_claim_count: int = 0
    dependent_claim_count: int = 0
    claims: list[PatentClaim] = Field(default_factory=list)
    source_doc_ids: list[str] = Field(default_factory=list)
    primary_source: IPSourceType = IPSourceType.USPTO


class FamilyJurisdictionCoverage(BaseModel):
    jurisdiction: str
    patent_count: int
    granted_count: int
    pending_count: int


class PatentFamily(BaseModel):
    """A patent family — the diligence unit, not the individual filing.

    Families are the right granularity for moat/FTO analysis because
    continuations, divisionals, and CIPs share priority and effectively
    extend the same exclusivity envelope.
    """

    family_id: str
    representative_title: str
    earliest_priority_date: date | None = None
    latest_expiration_estimate: date | None = None
    members: list[PatentRecord] = Field(default_factory=list)
    coverage: list[FamilyJurisdictionCoverage] = Field(default_factory=list)
    continuation_count: int = 0
    divisional_count: int = 0
    cip_count: int = 0
    independent_claims: list[PatentClaim] = Field(default_factory=list)
    dominant_claim_type: ClaimType = ClaimType.OTHER
    forward_citation_total: int = 0
    has_composition_claims: bool = False
    has_method_claims: bool = False
    has_device_claims: bool = False
    has_software_only_claims: bool = False
    assignees: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- adjacent IP signals


class PTABProceeding(BaseModel):
    proceeding_id: str
    patent_number: str
    type: Literal["IPR", "PGR", "CBM", "OTHER"] = "OTHER"
    petitioner: str | None = None
    filing_date: date | None = None
    status: str | None = None
    outcome: str | None = None
    source_doc_id: str


class LitigationRecord(BaseModel):
    docket_id: str
    court: str | None = None
    plaintiffs: list[str] = Field(default_factory=list)
    defendants: list[str] = Field(default_factory=list)
    patent_numbers: list[str] = Field(default_factory=list)
    filing_date: date | None = None
    status: str | None = None
    source_doc_id: str


class AssignmentEvent(BaseModel):
    assignment_id: str
    patent_or_application: str
    assignor: str | None = None
    assignee: str | None = None
    recorded_date: date | None = None
    nature: str | None = None
    source_doc_id: str


# --------------------------------------------------------------------------- verification


class IPVerificationState(str, Enum):
    VERIFIED = "verified"
    REPORTED = "reported"
    INFERRED = "inferred"
    REJECTED = "rejected"


class IPConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# --------------------------------------------------------------------------- scoring


class FrameworkScores(BaseModel):
    """One row of per-family framework scoring.

    Each component is on a 0–100 scale. The narrative renderer pulls
    these directly when explaining defensibility/moat/FTO posture.
    """

    claim_strength: float = Field(ge=0, le=100, default=0)
    moat: float = Field(ge=0, le=100, default=0)
    commercialization: float = Field(ge=0, le=100, default=0)
    differentiation: float = Field(ge=0, le=100, default=0)
    fto_risk: float = Field(ge=0, le=100, default=0)
    portfolio_quality: float = Field(ge=0, le=100, default=0)
    exclusivity: float = Field(ge=0, le=100, default=0)
    strategic_value: float = Field(ge=0, le=100, default=0)


class IPFinding(BaseModel):
    """A reportable IP statement bound to a family with citations.

    The renderer never emits text without an `IPFinding` (and citations)
    backing it. Findings are the atomic unit of the 5-page output.
    """

    finding_id: str
    family_id: str
    category: Literal[
        "executive",
        "portfolio",
        "claims_moat",
        "commercial_competitive",
        "risk_fto",
    ]
    text: str
    verification_state: IPVerificationState
    confidence: IPConfidence
    signal_score: float = Field(ge=0, le=100)
    framework_scores: FrameworkScores
    source_doc_ids: list[str] = Field(default_factory=list)
    citation_numbers: list[int] = Field(default_factory=list)


# --------------------------------------------------------------------------- report planning


class IPReportPlan(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    company_id: str
    requested_pages: int = Field(default=5, ge=1, le=8)
    soft_max_pages: int = 7
    hard_max_pages: int = 8
    english_only: bool = True
    style: Literal["institutional_print"] = "institutional_print"


class IPDiscoveryResult(BaseModel):
    company_id: str
    job_id: str
    records_collected: int
    records_persisted_new: int
    records_persisted_duplicate: int
    by_source: dict[IPSourceType, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    families_persisted: int = 0
    findings_persisted: int = 0
    report_id: str | None = None
