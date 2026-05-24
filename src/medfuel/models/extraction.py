from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "approval",
    "clearance",
    "designation",
    "clinical_hold",
    "warning",
    "inspection",
    "label_change",
    "trial_update",
    "patent_event",
    "offering_or_filing",
    "manufacturing_issue",
]


class VerificationState(str, Enum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    REPORTED_ONLY = "reported_only"
    REJECTED = "rejected"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CandidateEvent(BaseModel):
    """Raw extractor output, prior to normalization, dedupe, and verification."""

    agency: str
    jurisdiction: str
    event_type: EventType
    status: str
    summary: str
    event_date: date | None = None
    asset_name: str | None = None
    investor_importance: int = Field(default=3, ge=1, le=5)
    evidence_strength: int = Field(default=3, ge=1, le=5)
    source_doc_id: str
    source_excerpt: str | None = None
    extractor: str = "rule"


class RegulatoryEvent(BaseModel):
    """Normalized, de-duplicated regulatory fact."""

    event_id: str
    company_id: str
    asset_id: str | None = None
    agency: str
    jurisdiction: str
    event_type: EventType
    status: str
    event_date: date
    summary: str
    investor_importance: int = Field(ge=1, le=5)
    evidence_strength: int = Field(ge=1, le=5)
    source_doc_ids: list[str] = Field(default_factory=list)


class VerifiedClaim(BaseModel):
    """Reportable assertion tied to one event plus its citation set."""

    claim_id: str
    event_id: str
    text: str
    verification_state: VerificationState
    confidence: Confidence
    source_doc_ids: list[str]
    citation_numbers: list[int]
    signal_score: float = Field(ge=0, le=100)


class ReportPlan(BaseModel):
    company_id: str
    requested_pages: int = 4
    max_pages: int = 8
    english_only: bool = True
    style: Literal["institutional_print"] = "institutional_print"
    include_timeline: bool = True
    include_tables: bool = True
    include_callouts: bool = True
