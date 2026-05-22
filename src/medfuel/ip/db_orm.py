"""SQLAlchemy tables for the IP intelligence engine.

Lives in its own module so the regulatory schema in
medfuel.db.orm stays untouched. Both modules share the same
Base/metadata, so a single init_db() call creates everything.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from medfuel.db.orm import Base


class IPPatentRecordRow(Base):
    """One persisted patent or application from any IP source."""

    __tablename__ = "ip_patent_records"
    __table_args__ = (
        UniqueConstraint("company_id", "patent_id", name="uq_ip_patent_company"),
    )

    patent_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.company_id"), index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.job_id"), nullable=True, index=True
    )
    family_id: Mapped[str | None] = mapped_column(
        ForeignKey("ip_patent_families.family_id"), nullable=True, index=True
    )
    publication_number: Mapped[str | None] = mapped_column(String, index=True)
    application_number: Mapped[str | None] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String, default="utility")
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    grant_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiration_estimate: Mapped[date | None] = mapped_column(Date, nullable=True)
    legal_status: Mapped[str] = mapped_column(String, default="unknown")
    assignees: Mapped[list[str]] = mapped_column(JSON, default=list)
    inventors: Mapped[list[str]] = mapped_column(JSON, default=list)
    parent_publication_numbers: Mapped[list[str]] = mapped_column(JSON, default=list)
    cpc_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    forward_citations: Mapped[int] = mapped_column(Integer, default=0)
    backward_citations: Mapped[int] = mapped_column(Integer, default=0)
    independent_claim_count: Mapped[int] = mapped_column(Integer, default=0)
    dependent_claim_count: Mapped[int] = mapped_column(Integer, default=0)
    claims_payload: Mapped[list[dict]] = mapped_column(JSON, default=list)
    source_doc_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    primary_source: Mapped[str] = mapped_column(String, default="uspto")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IPPatentFamilyRow(Base):
    """A patent family — the moat/FTO analytical unit."""

    __tablename__ = "ip_patent_families"

    family_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.company_id"), index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.job_id"), nullable=True, index=True
    )
    representative_title: Mapped[str] = mapped_column(String)
    earliest_priority_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    latest_expiration_estimate: Mapped[date | None] = mapped_column(Date, nullable=True)
    coverage_payload: Mapped[list[dict]] = mapped_column(JSON, default=list)
    member_patent_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    continuation_count: Mapped[int] = mapped_column(Integer, default=0)
    divisional_count: Mapped[int] = mapped_column(Integer, default=0)
    cip_count: Mapped[int] = mapped_column(Integer, default=0)
    independent_claims_payload: Mapped[list[dict]] = mapped_column(JSON, default=list)
    dominant_claim_type: Mapped[str] = mapped_column(String, default="other")
    forward_citation_total: Mapped[int] = mapped_column(Integer, default=0)
    has_composition_claims: Mapped[bool] = mapped_column(Boolean, default=False)
    has_method_claims: Mapped[bool] = mapped_column(Boolean, default=False)
    has_device_claims: Mapped[bool] = mapped_column(Boolean, default=False)
    has_software_only_claims: Mapped[bool] = mapped_column(Boolean, default=False)
    assignees: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    framework_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    signal_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IPProceedingRow(Base):
    """PTAB proceedings and litigation tied to the company's patents."""

    __tablename__ = "ip_proceedings"

    proceeding_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.company_id"), index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.job_id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String, index=True)  # ptab | litigation | assignment
    patent_or_application: Mapped[str | None] = mapped_column(String, nullable=True)
    counterparty: Mapped[str | None] = mapped_column(String, nullable=True)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    source_doc_id: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IPFindingRow(Base):
    """A persisted IP finding — backs every sentence the narrator writes."""

    __tablename__ = "ip_findings"

    finding_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.company_id"), index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.job_id"), nullable=True, index=True
    )
    family_id: Mapped[str | None] = mapped_column(
        ForeignKey("ip_patent_families.family_id"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String, index=True)
    text: Mapped[str] = mapped_column(Text)
    verification_state: Mapped[str] = mapped_column(String, index=True)
    confidence: Mapped[str] = mapped_column(String)
    signal_score: Mapped[float] = mapped_column(Float, index=True)
    framework_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    source_doc_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    citation_numbers: Mapped[list[int]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IPReportRunRow(Base):
    """One run of the IP report builder."""

    __tablename__ = "ip_report_runs"

    report_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.company_id"), index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.job_id"), nullable=True, index=True
    )
    pages_requested: Mapped[int] = mapped_column(Integer, default=5)
    pages_rendered: Mapped[int] = mapped_column(Integer, default=5)
    soft_max_pages: Mapped[int] = mapped_column(Integer, default=7)
    hard_max_pages: Mapped[int] = mapped_column(Integer, default=8)
    adaptive_expansion_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    layout_plan: Mapped[dict] = mapped_column(JSON, default=dict)
    narrative_text: Mapped[str] = mapped_column(Text, default="")
    confidence_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    portfolio_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    narrative_model: Mapped[str | None] = mapped_column(String, nullable=True)
    extraction_model: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class IPCitationRow(Base):
    """Inline citation table for an IP report run."""

    __tablename__ = "ip_citations"

    citation_id: Mapped[str] = mapped_column(String, primary_key=True)
    report_id: Mapped[str] = mapped_column(
        ForeignKey("ip_report_runs.report_id"), index=True
    )
    finding_id: Mapped[str | None] = mapped_column(
        ForeignKey("ip_findings.finding_id"), nullable=True
    )
    inline_number: Mapped[int] = mapped_column(Integer)
    source_doc_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.source_doc_id")
    )
    url: Mapped[str] = mapped_column(String)
    locator: Mapped[str | None] = mapped_column(String, nullable=True)
    source_confidence: Mapped[str] = mapped_column(String, default="medium")
    evidence_kind: Mapped[str] = mapped_column(String, default="patent")
