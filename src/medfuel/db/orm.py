from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CompanyRow(Base):
    __tablename__ = "companies"

    company_id: Mapped[str] = mapped_column(String, primary_key=True)
    legal_name: Mapped[str] = mapped_column(String, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    ticker: Mapped[str | None] = mapped_column(String, nullable=True)
    cik: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    domains: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    documents: Mapped[list[SourceDocumentRow]] = relationship(back_populates="company")


class JobRow(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.company_id"), index=True)
    status: Mapped[str] = mapped_column(String, default="queued")
    requested_pages: Mapped[int] = mapped_column(Integer, default=6)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class SourceDocumentRow(Base):
    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint("company_id", "content_hash", name="uq_company_content_hash"),
    )

    source_doc_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.company_id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.job_id"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String, index=True)
    jurisdiction: Mapped[str] = mapped_column(String, index=True)
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    page_locator: Mapped[str | None] = mapped_column(String, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    official_rank: Mapped[int] = mapped_column(Integer, nullable=False)

    company: Mapped[CompanyRow] = relationship(back_populates="documents")


class AssetRow(Base):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("company_id", "name_key", name="uq_asset_name"),)

    asset_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.company_id"), index=True)
    asset_name: Mapped[str] = mapped_column(String, nullable=False)
    name_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    modality: Mapped[str | None] = mapped_column(String, nullable=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExtractionRow(Base):
    """Raw extractor output kept for audit/replay."""

    __tablename__ = "extractions"

    extraction_id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.job_id"), index=True, nullable=True)
    source_doc_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.source_doc_id"), index=True
    )
    extractor: Mapped[str] = mapped_column(String, nullable=False)
    model_id: Mapped[str | None] = mapped_column(String, nullable=True)
    schema_version: Mapped[str] = mapped_column(String, default="v1")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RegulatoryEventRow(Base):
    __tablename__ = "regulatory_events"
    __table_args__ = (
        UniqueConstraint("company_id", "event_key", name="uq_event_key"),
    )

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.company_id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.job_id"), index=True, nullable=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.asset_id"), nullable=True)
    agency: Mapped[str] = mapped_column(String, index=True)
    jurisdiction: Mapped[str] = mapped_column(String, index=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    summary: Mapped[str] = mapped_column(Text)
    investor_importance: Mapped[int] = mapped_column(Integer)
    evidence_strength: Mapped[int] = mapped_column(Integer)
    source_doc_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    event_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ClaimRow(Base):
    __tablename__ = "claims"

    claim_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("regulatory_events.event_id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    verification_state: Mapped[str] = mapped_column(String, index=True)
    confidence: Mapped[str] = mapped_column(String)
    source_doc_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    citation_numbers: Mapped[list[int]] = mapped_column(JSON, default=list)
    signal_score: Mapped[float] = mapped_column(Float, index=True)


class CitationRow(Base):
    __tablename__ = "citations"

    citation_id: Mapped[str] = mapped_column(String, primary_key=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("report_runs.report_id"), index=True)
    claim_id: Mapped[str | None] = mapped_column(ForeignKey("claims.claim_id"), nullable=True)
    inline_number: Mapped[int] = mapped_column(Integer)
    source_doc_id: Mapped[str] = mapped_column(ForeignKey("source_documents.source_doc_id"))
    url: Mapped[str] = mapped_column(String)
    locator: Mapped[str | None] = mapped_column(String, nullable=True)
    source_confidence: Mapped[str] = mapped_column(String, default="medium")


class ReportRunRow(Base):
    __tablename__ = "report_runs"

    report_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.company_id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.job_id"), index=True, nullable=True)
    pages_requested: Mapped[int] = mapped_column(Integer, default=6)
    pages_rendered: Mapped[int] = mapped_column(Integer, default=6)
    adaptive_expansion_triggered: Mapped[bool] = mapped_column(default=False)
    layout_plan: Mapped[dict] = mapped_column(JSON, default=dict)
    narrative_text: Mapped[str] = mapped_column(Text, default="")
    confidence_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    narrative_model: Mapped[str | None] = mapped_column(String, nullable=True)
    extraction_model: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    audit_id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String, index=True)
    entity_id: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String, default="system")
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    before_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    after_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
