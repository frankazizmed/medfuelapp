"""Init Clinical Evidence island schema.

Revision ID: 0001_init_ce
Revises:
Create Date: 2026-05-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "0001_init_ce"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "ce_company_context",
        sa.Column("company_id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("tickers", ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("indications", ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("assets", ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "ce_section_runs",
        sa.Column("run_id", sa.String, primary_key=True),
        sa.Column("company_id", sa.String, sa.ForeignKey("ce_company_context.company_id")),
        sa.Column("status", sa.String, nullable=False, server_default="queued"),
        sa.Column("error", sa.Text),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_ce_section_runs_company", "ce_section_runs", ["company_id"])

    op.create_table(
        "ce_documents",
        sa.Column("doc_id", sa.String, primary_key=True),
        sa.Column("company_id", sa.String, nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("extra", JSONB, nullable=False, server_default="{}"),
        sa.Column("sha256", sa.String, nullable=False, unique=True),
        sa.Column("fetched_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_ce_documents_company", "ce_documents", ["company_id"])

    op.create_table(
        "ce_trials",
        sa.Column("trial_id", sa.String, primary_key=True),
        sa.Column("company_id", sa.String, nullable=False),
        sa.Column("nct_id", sa.String),
        sa.Column("title", sa.Text),
        sa.Column("phase", sa.String, server_default="unknown"),
        sa.Column("indication", sa.Text),
        sa.Column("enrollment", sa.Integer),
        sa.Column("randomized", sa.Boolean),
        sa.Column("blinded", sa.Boolean),
        sa.Column("placebo_controlled", sa.Boolean),
        sa.Column("primary_endpoints", ARRAY(sa.String), server_default="{}"),
        sa.Column("secondary_endpoints", ARRAY(sa.String), server_default="{}"),
        sa.Column("status", sa.String),
        sa.Column("start_date", sa.String),
        sa.Column("primary_completion_date", sa.String),
        sa.Column("source_doc_ids", ARRAY(sa.String), server_default="{}"),
    )
    op.create_index("ix_ce_trials_company", "ce_trials", ["company_id"])
    op.create_index("ix_ce_trials_nct", "ce_trials", ["nct_id"])

    op.create_table(
        "ce_publications",
        sa.Column("pub_id", sa.String, primary_key=True),
        sa.Column("company_id", sa.String, nullable=False),
        sa.Column("doi", sa.String),
        sa.Column("pmid", sa.String),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("journal", sa.Text),
        sa.Column("year", sa.Integer),
        sa.Column("authors", ARRAY(sa.String), server_default="{}"),
        sa.Column("linked_nct_ids", ARRAY(sa.String), server_default="{}"),
        sa.Column("source_doc_id", sa.String, nullable=False),
    )
    op.create_index("ix_ce_publications_company", "ce_publications", ["company_id"])
    op.create_index("ix_ce_publications_pmid", "ce_publications", ["pmid"])

    op.create_table(
        "ce_findings",
        sa.Column("finding_id", sa.String, primary_key=True),
        sa.Column("company_id", sa.String, nullable=False),
        sa.Column("run_id", sa.String),
        sa.Column("trial_id", sa.String),
        sa.Column("pub_id", sa.String),
        sa.Column("source_doc_id", sa.String, nullable=False),
        sa.Column("finding_type", sa.String, nullable=False),
        sa.Column("endpoint", sa.Text),
        sa.Column("endpoint_type", sa.String, server_default="unknown"),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("raw_excerpt", sa.Text),
        sa.Column("result_measure", sa.Text),
        sa.Column("result_value", sa.Float),
        sa.Column("result_units", sa.String),
        sa.Column("p_value", sa.Float),
        sa.Column("ci_low", sa.Float),
        sa.Column("ci_high", sa.Float),
        sa.Column("n", sa.Integer),
        sa.Column("follow_up_months", sa.Float),
        sa.Column("verification_status", sa.String, server_default="REPORTED"),
        sa.Column("scores", JSONB, server_default="{}"),
        sa.Column("risk_flags", ARRAY(sa.String), server_default="{}"),
    )
    op.create_index("ix_ce_findings_company", "ce_findings", ["company_id"])
    op.create_index("ix_ce_findings_run", "ce_findings", ["run_id"])

    op.create_table(
        "ce_section_payloads",
        sa.Column("run_id", sa.String, primary_key=True),
        sa.Column("company_id", sa.String, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("generated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_ce_section_payloads_company", "ce_section_payloads", ["company_id"])

    op.create_table(
        "ce_doc_chunks",
        sa.Column("chunk_id", sa.String, primary_key=True),
        sa.Column("doc_id", sa.String, sa.ForeignKey("ce_documents.doc_id"), nullable=False),
        sa.Column("company_id", sa.String, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", sa.dialects.postgresql.ARRAY(sa.Float), nullable=True),
    )
    op.execute(
        "ALTER TABLE ce_doc_chunks ALTER COLUMN embedding TYPE vector(3072) USING NULL"
    )
    op.create_index("ix_ce_doc_chunks_doc", "ce_doc_chunks", ["doc_id"])


def downgrade() -> None:
    op.drop_table("ce_doc_chunks")
    op.drop_table("ce_section_payloads")
    op.drop_table("ce_findings")
    op.drop_table("ce_publications")
    op.drop_table("ce_trials")
    op.drop_table("ce_documents")
    op.drop_table("ce_section_runs")
    op.drop_table("ce_company_context")
