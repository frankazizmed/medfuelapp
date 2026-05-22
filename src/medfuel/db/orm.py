from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
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
