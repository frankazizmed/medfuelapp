from __future__ import annotations

from datetime import UTC, datetime

import pytest

from medfuel.adapters.base import SourceAdapter
from medfuel.db.registry import hash_payload
from medfuel.ip.db_orm import (
    IPCitationRow,
    IPFindingRow,
    IPPatentFamilyRow,
    IPPatentRecordRow,
    IPProceedingRow,
    IPReportRunRow,
)
from medfuel.ip.ingest.pipeline import IPDiscoveryPipeline, run_ip_discovery
from medfuel.models import CompanyIdentity, JurisdictionScope, RawSourceRecord, SourceType
from medfuel.models.schemas import OFFICIAL_RANK


def _record(source: SourceType, url: str, payload: dict, title: str = "t") -> RawSourceRecord:
    return RawSourceRecord(
        source_type=source,
        jurisdiction="US",
        url=url,
        title=title,
        payload=payload,
        retrieved_at=datetime.now(UTC),
        content_hash=hash_payload(url, payload, title=title),
        official_rank=OFFICIAL_RANK[source],
    )


class _StubAdapter(SourceAdapter):
    def __init__(self, source_type: SourceType, records: list[RawSourceRecord]):
        self.source_type = source_type
        self.jurisdiction = "US"
        self._records = records

    async def discover(self, identity, scope):
        return list(self._records)


@pytest.mark.asyncio
async def test_full_ip_pipeline_persists_families_findings_and_report(db_session):
    patentsview_records = [
        _record(
            SourceType.PATENTSVIEW,
            "https://search.patentsview.org/api/v1/patent/?p=10000001",
            {
                "patent_id": "10000001",
                "patent_number": "10000001",
                "patent_title": "Anti-Examplon antibody composition",
                "patent_date": "2024-08-01",
                "patent_num_cited_by_us_patents": 18,
                "patent_num_us_patent_citations": 40,
                "assignees": [{"assignee_organization": "Example Tx"}],
                "claims": [
                    {
                        "claim_number": 1,
                        "claim_text": "A composition comprising an antibody against Examplon.",
                        "claim_dependent": False,
                    },
                    {
                        "claim_number": 2,
                        "claim_text": "A method of treating cancer comprising administering the composition of claim 1.",
                        "claim_dependent": False,
                    },
                ],
            },
            title="PV patent 10000001",
        ),
        _record(
            SourceType.PATENTSVIEW,
            "https://search.patentsview.org/api/v1/patent/?p=10500001",
            {
                "patent_id": "10500001",
                "patent_number": "10500001",
                "patent_title": "Anti-Examplon antibody composition (continuation)",
                "patent_date": "2024-12-01",
                "patent_num_cited_by_us_patents": 3,
                "patent_num_us_patent_citations": 12,
                "assignees": [{"assignee_organization": "Example Tx"}],
                "claims": [
                    {
                        "claim_number": 1,
                        "claim_text": "A composition comprising an antibody against Examplon and a stabilizer.",
                        "claim_dependent": False,
                    }
                ],
            },
            title="PV patent 10500001",
        ),
    ]
    uspto_record = [
        _record(
            SourceType.USPTO,
            "https://api.uspto.gov/ds-api/oa_actions/v1/records?p=10000001",
            {
                "patentNumber": "10000001",
                "inventionTitle": "Anti-Examplon antibody composition",
                "patentDate": "2024-08-01",
                "filingDate": "2018-01-15",
                "patentAssignee": "Example Tx",
            },
        )
    ]
    ptab_record = [
        _record(
            SourceType.PTAB,
            "https://acts.uspto.gov/oss-web/searchOSS#/proceedings/IPR2024-00001",
            {
                "proceedingNumber": "IPR2024-00001",
                "respondentPatentNumber": "10000001",
                "proceedingTypeCategory": "Inter Partes Review (IPR)",
                "petitionerPartyName": "Competitor Inc.",
                "filingDate": "2024-02-01",
                "currentStatus": "Instituted",
            },
            title="PTAB IPR2024-00001",
        )
    ]

    pipeline = IPDiscoveryPipeline(
        adapters=[
            _StubAdapter(SourceType.PATENTSVIEW, patentsview_records),
            _StubAdapter(SourceType.USPTO, uspto_record),
            _StubAdapter(SourceType.PTAB, ptab_record),
        ]
    )

    result = await run_ip_discovery(
        identity=CompanyIdentity(name="Example Tx"),
        scope=JurisdictionScope(
            sources=[SourceType.PATENTSVIEW, SourceType.USPTO, SourceType.PTAB]
        ),
        pipeline=pipeline,
        session=db_session,
    )

    assert result.records_persisted_new == 4
    assert result.families_persisted >= 1
    assert result.report_id is not None
    assert result.report_id.startswith("iprpt_")

    families = db_session.query(IPPatentFamilyRow).all()
    assert families, "expected at least one persisted family"
    assert any(f.has_composition_claims for f in families)
    assert any(f.has_method_claims for f in families)

    patents = db_session.query(IPPatentRecordRow).all()
    assert patents
    assert all(p.family_id is not None for p in patents)

    findings = db_session.query(IPFindingRow).all()
    assert findings
    assert {f.category for f in findings} >= {"executive", "portfolio", "claims_moat", "commercial_competitive", "risk_fto"}

    citations = (
        db_session.query(IPCitationRow)
        .filter(IPCitationRow.report_id == result.report_id)
        .all()
    )
    assert citations, "expected citations from PatentsView/USPTO docs"

    report = db_session.get(IPReportRunRow, result.report_id)
    assert report is not None
    assert report.pages_rendered >= 5
    assert "IP Diligence" in report.narrative_text
    assert "IP Executive Summary" in report.narrative_text
    assert "Portfolio Architecture" in report.narrative_text
    assert "Claim Strength and Moat" in report.narrative_text
    assert "Commercial and Competitive Implications" in report.narrative_text
    assert "Key Risks and FTO" in report.narrative_text
    assert report.portfolio_summary["family_count"] == len(families)

    proceedings = db_session.query(IPProceedingRow).all()
    assert any(p.kind == "ptab" for p in proceedings)


@pytest.mark.asyncio
async def test_ip_pipeline_handles_no_patents_gracefully(db_session):
    pipeline = IPDiscoveryPipeline(adapters=[])
    result = await run_ip_discovery(
        identity=CompanyIdentity(name="No Patent Co"),
        scope=JurisdictionScope(sources=[SourceType.USPTO]),
        pipeline=pipeline,
        session=db_session,
    )
    assert result.families_persisted == 0
    assert result.report_id is not None
    report = db_session.get(IPReportRunRow, result.report_id)
    assert report is not None
    assert "No patent families discovered" in report.narrative_text
    assert report.status == "complete_empty"
