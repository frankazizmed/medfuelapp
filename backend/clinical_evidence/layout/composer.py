"""Compose the final SectionPayload (the island's public output)."""

from __future__ import annotations

from datetime import datetime, timezone

from clinical_evidence.config import get_settings
from clinical_evidence.schemas import (
    Citation,
    ClinicalFinding,
    Page,
    SectionPayload,
    Trial,
)


def compose(
    *,
    run_id: str,
    company_id: str,
    company_name: str,
    pages: list[Page],
    citations: list[Citation],
    omitted_fraction: float,
    page_count: int,
) -> SectionPayload:
    settings = get_settings()
    return SectionPayload(
        run_id=run_id,
        company_id=company_id,
        company_name=company_name,
        pages=pages,
        citations=citations,
        page_count=page_count,
        expanded_from_default=page_count > settings.default_page_target,
        omitted_high_signal_fraction=omitted_fraction,
        generated_at=datetime.now(timezone.utc),
        model_versions={
            "extraction": settings.extraction_model,
            "narrative": settings.narrative_model,
            "embedding": settings.embedding_model,
        },
    )
