from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from medfuel.db.orm import (
    ClaimRow,
    CompanyRow,
    RegulatoryEventRow,
)
from medfuel.models import ReportPlan
from medfuel.render.report import CitationResolveError, ReportBuilder


def _seed_company_event_claim(session: Session) -> None:
    session.add(CompanyRow(company_id="cmp_inv", legal_name="Invariant Test"))
    session.add(
        RegulatoryEventRow(
            event_id="evt_inv",
            company_id="cmp_inv",
            agency="FDA",
            jurisdiction="US",
            event_type="approval",
            status="AP",
            event_date=date(2025, 1, 1),
            summary="approval",
            investor_importance=5,
            evidence_strength=5,
            source_doc_ids=["src_missing"],  # intentionally references a nonexistent doc
            event_key="evt_inv_key",
        )
    )
    session.add(
        ClaimRow(
            claim_id="clm_inv",
            event_id="evt_inv",
            text="claim",
            verification_state="verified",
            confidence="high",
            source_doc_ids=["src_missing"],
            citation_numbers=[],
            signal_score=90.0,
        )
    )
    session.commit()


@pytest.mark.asyncio
async def test_report_builder_raises_when_claims_have_no_resolvable_citations(db_session):
    _seed_company_event_claim(db_session)
    builder = ReportBuilder(db_session)
    with pytest.raises(CitationResolveError):
        await builder.build(
            company_id="cmp_inv",
            job_id=None,
            plan=ReportPlan(company_id="cmp_inv"),
        )
