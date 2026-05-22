"""Pydantic contract for the Clinical Evidence island.

Single source of truth used by every layer (discovery → narrative → render).
The host app interacts with the island via CompanyContext (input) and
SectionPayload (output). Everything else is internal.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


# Host-facing contract ------------------------------------------------------


class CompanyContext(BaseModel):
    company_id: str
    name: str
    tickers: list[str] = Field(default_factory=list)
    indications: list[str] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)


class RunStatus(str, Enum):
    queued = "queued"
    discovering = "discovering"
    ingesting = "ingesting"
    extracting = "extracting"
    verifying = "verifying"
    scoring = "scoring"
    generating = "generating"
    laying_out = "laying_out"
    ready = "ready"
    failed = "failed"


class RunState(BaseModel):
    run_id: str
    company_id: str
    status: RunStatus
    started_at: datetime
    updated_at: datetime
    error: Optional[str] = None


# Verification + signal vocabulary -----------------------------------------


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"      # confirmed across ≥2 independent sources
    REPORTED = "REPORTED"      # appears in a single primary source
    INFERRED = "INFERRED"      # derived/computed, not directly stated


class TrialPhase(str, Enum):
    preclinical = "preclinical"
    phase1 = "phase1"
    phase1_2 = "phase1_2"
    phase2 = "phase2"
    phase2_3 = "phase2_3"
    phase3 = "phase3"
    phase4 = "phase4"
    unknown = "unknown"


class EndpointType(str, Enum):
    hard = "hard"              # mortality, MACE, hospitalization, disease progression
    surrogate = "surrogate"    # biomarker, imaging, PRO
    composite = "composite"
    unknown = "unknown"


class FindingType(str, Enum):
    efficacy = "efficacy"
    safety = "safety"
    design = "design"
    durability = "durability"
    subgroup = "subgroup"
    regulatory = "regulatory"
    pharmacology = "pharmacology"
    comparator = "comparator"


# Source documents ---------------------------------------------------------


class SourceKind(str, Enum):
    clinicaltrials = "clinicaltrials"
    pubmed = "pubmed"
    fda = "fda"
    ema = "ema"
    sec = "sec"
    company_web = "company_web"
    investor_deck = "investor_deck"
    conference = "conference"
    press_release = "press_release"
    preprint = "preprint"
    other = "other"


class RawDocument(BaseModel):
    doc_id: str
    company_id: str
    source: SourceKind
    url: str
    title: Optional[str] = None
    fetched_at: datetime
    text: str
    metadata: dict = Field(default_factory=dict)
    sha256: str


class Trial(BaseModel):
    trial_id: str
    company_id: str
    nct_id: Optional[str] = None
    title: Optional[str] = None
    phase: TrialPhase = TrialPhase.unknown
    indication: Optional[str] = None
    enrollment: Optional[int] = None
    randomized: Optional[bool] = None
    blinded: Optional[bool] = None
    placebo_controlled: Optional[bool] = None
    primary_endpoints: list[str] = Field(default_factory=list)
    secondary_endpoints: list[str] = Field(default_factory=list)
    status: Optional[str] = None
    start_date: Optional[str] = None
    primary_completion_date: Optional[str] = None
    source_doc_ids: list[str] = Field(default_factory=list)


class Publication(BaseModel):
    pub_id: str
    company_id: str
    doi: Optional[str] = None
    pmid: Optional[str] = None
    title: str
    journal: Optional[str] = None
    year: Optional[int] = None
    authors: list[str] = Field(default_factory=list)
    linked_nct_ids: list[str] = Field(default_factory=list)
    source_doc_id: str


# The atomic unit of clinical intelligence ---------------------------------


class StatisticalResult(BaseModel):
    measure: Optional[str] = None        # e.g. "Δ HbA1c (%)", "HR", "RR"
    value: Optional[float] = None
    units: Optional[str] = None
    p_value: Optional[float] = None
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    n: Optional[int] = None


class SignalScores(BaseModel):
    """Nine institutional-investor relevance scores (0..1 each). See Section 6."""

    evidence_strength: float = 0.0
    endpoint_quality: float = 0.0
    statistical_robustness: float = 0.0
    physician_relevance: float = 0.0
    commercialization_relevance: float = 0.0
    differentiation: float = 0.0
    safety_concern: float = 0.0          # higher = more concerning
    regulatory_relevance: float = 0.0
    durability: float = 0.0

    def composite(self) -> float:
        """Weighted composite used by the ranker and page-budget engine."""
        weights = {
            "evidence_strength": 0.18,
            "endpoint_quality": 0.14,
            "statistical_robustness": 0.14,
            "physician_relevance": 0.10,
            "commercialization_relevance": 0.10,
            "differentiation": 0.10,
            "regulatory_relevance": 0.10,
            "durability": 0.08,
            "safety_concern": 0.06,
        }
        total = sum(getattr(self, k) * v for k, v in weights.items())
        return round(total, 4)


class RiskFlag(str, Enum):
    underpowered = "underpowered"
    weak_comparator = "weak_comparator"
    open_label = "open_label"
    surrogate_endpoint = "surrogate_endpoint"
    high_dropout = "high_dropout"
    confounding = "confounding"
    subgroup_dependence = "subgroup_dependence"
    single_site = "single_site"
    enrollment_risk = "enrollment_risk"
    safety_signal = "safety_signal"
    durability_concern = "durability_concern"
    statistical_fragility = "statistical_fragility"
    endpoint_mismatch = "endpoint_mismatch"
    publication_gap = "publication_gap"
    inconsistent = "inconsistent"


class ClinicalFinding(BaseModel):
    """One atomic clinical claim extracted from source documents.

    Carries everything needed to score it, render it, and cite it.
    """

    model_config = ConfigDict(use_enum_values=True)

    finding_id: str
    company_id: str
    trial_id: Optional[str] = None
    pub_id: Optional[str] = None
    source_doc_id: str

    finding_type: FindingType
    endpoint: Optional[str] = None
    endpoint_type: EndpointType = EndpointType.unknown
    description: str
    result: Optional[StatisticalResult] = None
    follow_up_months: Optional[float] = None

    verification_status: VerificationStatus = VerificationStatus.REPORTED
    scores: SignalScores = Field(default_factory=SignalScores)
    risk_flags: list[RiskFlag] = Field(default_factory=list)

    raw_excerpt: Optional[str] = None    # short verbatim quote for traceability


# Citations ----------------------------------------------------------------


class Citation(BaseModel):
    number: int
    doc_id: str
    url: str
    title: Optional[str] = None
    source: SourceKind
    confidence: float = Field(ge=0, le=1)
    evidence_strength: float = Field(ge=0, le=1)


# Page blocks (typed UI primitives) ---------------------------------------


class BaseBlock(BaseModel):
    kind: str
    citation_numbers: list[int] = Field(default_factory=list)


class ParagraphBlock(BaseBlock):
    kind: Literal["paragraph"] = "paragraph"
    text: str


class HeadingBlock(BaseBlock):
    kind: Literal["heading"] = "heading"
    text: str
    level: int = 2


class EndpointTableRow(BaseModel):
    endpoint: str
    endpoint_type: EndpointType
    arm: Optional[str] = None
    result: Optional[str] = None
    p_value: Optional[float] = None
    ci: Optional[str] = None
    n: Optional[int] = None
    citation_numbers: list[int] = Field(default_factory=list)


class EndpointTableBlock(BaseBlock):
    kind: Literal["endpoint_table"] = "endpoint_table"
    title: str
    rows: list[EndpointTableRow]


class SafetyHeatmapRow(BaseModel):
    event: str
    rate_treatment: Optional[float] = None
    rate_control: Optional[float] = None
    severity: Literal["mild", "moderate", "severe", "sae"] = "moderate"
    citation_numbers: list[int] = Field(default_factory=list)


class SafetyHeatmapBlock(BaseBlock):
    kind: Literal["safety_heatmap"] = "safety_heatmap"
    title: str
    rows: list[SafetyHeatmapRow]


class CalloutBlock(BaseBlock):
    kind: Literal["callout"] = "callout"
    tone: Literal["signal", "risk", "neutral"] = "neutral"
    title: str
    text: str


class TrialTimelineEntry(BaseModel):
    label: str
    phase: TrialPhase
    start: Optional[str] = None
    end: Optional[str] = None
    status: Optional[str] = None
    citation_numbers: list[int] = Field(default_factory=list)


class TrialTimelineBlock(BaseBlock):
    kind: Literal["trial_timeline"] = "trial_timeline"
    title: str
    entries: list[TrialTimelineEntry]


class EvidenceHierarchyEntry(BaseModel):
    label: str
    weight: float
    verification: VerificationStatus
    citation_numbers: list[int] = Field(default_factory=list)


class EvidenceHierarchyBlock(BaseBlock):
    kind: Literal["evidence_hierarchy"] = "evidence_hierarchy"
    title: str
    entries: list[EvidenceHierarchyEntry]


PageBlock = Union[
    ParagraphBlock,
    HeadingBlock,
    EndpointTableBlock,
    SafetyHeatmapBlock,
    CalloutBlock,
    TrialTimelineBlock,
    EvidenceHierarchyBlock,
]


class Page(BaseModel):
    index: int                            # 1-indexed page number
    title: str                            # e.g. "Clinical Executive Summary"
    blocks: list[PageBlock]


class SectionPayload(BaseModel):
    """The island's final output. The host renders this with one component."""

    run_id: str
    company_id: str
    company_name: str
    pages: list[Page]
    citations: list[Citation]
    page_count: int
    expanded_from_default: bool
    omitted_high_signal_fraction: float
    generated_at: datetime
    model_versions: dict[str, str]


# Discovery + ingestion contracts -----------------------------------------


class DiscoveryResult(BaseModel):
    trials: list[Trial] = Field(default_factory=list)
    publications: list[Publication] = Field(default_factory=list)
    documents: list[RawDocument] = Field(default_factory=list)


# Narrative-layer intermediates --------------------------------------------


class PageBrief(BaseModel):
    """What we hand Claude per page — only structured, ranked, verified evidence."""

    index: int
    title: str
    page_role: str                        # e.g. "clinical_executive_summary"
    findings: list[ClinicalFinding]
    extra_context: dict = Field(default_factory=dict)
