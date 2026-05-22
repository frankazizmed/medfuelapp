"""SQLAlchemy ORM models for the Clinical Evidence island.

All tables are prefixed ce_ so the island never collides with the host
schema. pgvector is used only for the embeddings table.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CECompanyContext(Base):
    __tablename__ = "ce_company_context"

    company_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    tickers: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    indications: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    assets: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CESectionRun(Base):
    __tablename__ = "ce_section_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, ForeignKey("ce_company_context.company_id"))
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CEDocument(Base):
    __tablename__ = "ce_documents"

    doc_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    sha256: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CETrial(Base):
    __tablename__ = "ce_trials"

    trial_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, index=True)
    nct_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    phase: Mapped[str] = mapped_column(String, default="unknown")
    indication: Mapped[str | None] = mapped_column(Text, nullable=True)
    enrollment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    randomized: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    blinded: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    placebo_controlled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    primary_endpoints: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    secondary_endpoints: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    start_date: Mapped[str | None] = mapped_column(String, nullable=True)
    primary_completion_date: Mapped[str | None] = mapped_column(String, nullable=True)
    source_doc_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)


class CEPublication(Base):
    __tablename__ = "ce_publications"

    pub_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, index=True)
    doi: Mapped[str | None] = mapped_column(String, nullable=True)
    pmid: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    journal: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    authors: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    linked_nct_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    source_doc_id: Mapped[str] = mapped_column(String, nullable=False)


class CEFinding(Base):
    __tablename__ = "ce_findings"

    finding_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, index=True)
    run_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    trial_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    pub_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source_doc_id: Mapped[str] = mapped_column(String, nullable=False)

    finding_type: Mapped[str] = mapped_column(String, nullable=False)
    endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    endpoint_type: Mapped[str] = mapped_column(String, default="unknown")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    raw_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    result_measure: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_units: Mapped[str | None] = mapped_column(String, nullable=True)
    p_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    ci_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    ci_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    follow_up_months: Mapped[float | None] = mapped_column(Float, nullable=True)

    verification_status: Mapped[str] = mapped_column(String, default="REPORTED")
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_flags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)


class CESectionPayload(Base):
    __tablename__ = "ce_section_payloads"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
