from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from medfuel.adapters.base import SourceAdapter
from medfuel.db.orm import Base
from medfuel.db.registry import hash_payload
from medfuel.ip import db_orm as _ip_db_orm  # noqa: F401 - register IP tables
from medfuel.ip.api.routes import get_db
from medfuel.ip.ingest import pipeline as ip_pipeline_mod
from medfuel.main import create_app
from medfuel.models.schemas import OFFICIAL_RANK, RawSourceRecord, SourceType


class _StubPatentsViewAdapter(SourceAdapter):
    source_type = SourceType.PATENTSVIEW
    jurisdiction = "US"

    async def discover(self, identity, scope):
        url = "https://search.patentsview.org/api/v1/patent/?p=10000001"
        payload = {
            "patent_id": "10000001",
            "patent_number": "10000001",
            "patent_title": "Composition X",
            "patent_date": "2024-08-01",
            "assignees": [{"assignee_organization": identity.name}],
            "claims": [
                {
                    "claim_number": 1,
                    "claim_text": "A composition comprising X.",
                    "claim_dependent": False,
                }
            ],
        }
        return [
            RawSourceRecord(
                source_type=self.source_type,
                jurisdiction=self.jurisdiction,
                url=url,
                title="PV 10000001",
                payload=payload,
                retrieved_at=datetime.now(UTC),
                content_hash=hash_payload(url, payload, title="PV"),
                official_rank=OFFICIAL_RANK[self.source_type],
            )
        ]


@pytest.fixture()
def client(monkeypatch) -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def override_db() -> Iterator[Session]:
        session = Session_()
        try:
            yield session
        finally:
            session.close()

    real_pipeline_cls = ip_pipeline_mod.IPDiscoveryPipeline

    def fake_pipeline_factory(*args, **kwargs):
        if "adapters" in kwargs or args:
            return real_pipeline_cls(*args, **kwargs)
        return real_pipeline_cls(adapters=[_StubPatentsViewAdapter()])

    def fake_sessionmaker():
        return Session_

    monkeypatch.setattr(ip_pipeline_mod, "IPDiscoveryPipeline", fake_pipeline_factory)
    monkeypatch.setattr(ip_pipeline_mod, "get_sessionmaker", fake_sessionmaker)

    app = create_app()
    app.dependency_overrides[get_db] = override_db

    from medfuel.ip.api import routes as ip_routes_mod

    monkeypatch.setattr(ip_routes_mod, "_session", lambda: Session_())

    with TestClient(app) as c:
        yield c


def test_ip_job_creates_and_completes(client):
    payload = {
        "company": {"name": "Example Tx"},
        "scope": {
            "sources": ["patentsview"],
            "jurisdictions": ["US"],
            "lookback_years": 10,
        },
        "report_plan": {"requested_pages": 5, "soft_max_pages": 7, "hard_max_pages": 8},
    }
    resp = client.post("/v1/ip/jobs", json=payload)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    assert job_id.startswith("job_")

    status_resp = client.get(f"/v1/ip/jobs/{job_id}")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"].startswith("complete")
    summary = body["result_summary"]
    assert summary["families_persisted"] >= 1
    assert summary["report_id"].startswith("iprpt_")


def test_ip_report_endpoints(client):
    payload = {
        "company": {"name": "Example Tx"},
        "scope": {"sources": ["patentsview"], "jurisdictions": ["US"], "lookback_years": 10},
    }
    job_resp = client.post("/v1/ip/jobs", json=payload).json()
    status = client.get(f"/v1/ip/jobs/{job_resp['job_id']}").json()
    report_id = status["result_summary"]["report_id"]

    rpt = client.get(f"/v1/ip/reports/{report_id}").json()
    assert rpt["pages_rendered"] >= 5
    assert any(
        s["slug"] == "ip_executive" for s in rpt["layout_plan"]["sections"]
    )

    narr = client.get(f"/v1/ip/reports/{report_id}/narrative").text
    assert "IP Executive Summary" in narr

    cites = client.get(f"/v1/ip/reports/{report_id}/citations").json()
    assert cites["citations"]

    findings = client.get(f"/v1/ip/reports/{report_id}/findings").json()
    assert findings
    assert any(f["category"] == "executive" for f in findings)


def test_ip_rerender_creates_new_report_run(client):
    payload = {
        "company": {"name": "Example Tx"},
        "scope": {"sources": ["patentsview"], "jurisdictions": ["US"], "lookback_years": 10},
    }
    job_resp = client.post("/v1/ip/jobs", json=payload).json()
    status = client.get(f"/v1/ip/jobs/{job_resp['job_id']}").json()
    original_id = status["result_summary"]["report_id"]

    rerender = client.post(
        f"/v1/ip/reports/{original_id}/rerender",
        json={"requested_pages": 7, "soft_max_pages": 7, "hard_max_pages": 8},
    )
    assert rerender.status_code == 200
    new = rerender.json()
    assert new["report_id"] != original_id
    assert new["pages_requested"] == 7


def test_unknown_ip_report_returns_404(client):
    resp = client.get("/v1/ip/reports/iprpt_missing")
    assert resp.status_code == 404
