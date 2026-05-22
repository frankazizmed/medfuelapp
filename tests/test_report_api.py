from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from medfuel.adapters.base import SourceAdapter
from medfuel.api.routes import get_db
from medfuel.db.orm import Base
from medfuel.db.registry import hash_payload
from medfuel.ingest import pipeline as pipeline_mod
from medfuel.main import create_app
from medfuel.models import RawSourceRecord, SourceType
from medfuel.models.schemas import OFFICIAL_RANK


class _FDAStubAdapter(SourceAdapter):
    source_type = SourceType.FDA
    jurisdiction = "US"

    async def discover(self, identity, scope):
        url = "https://api.fda.gov/device/510k.json?stub=1"
        payload = {
            "k_number": "K991234",
            "device_name": f"{identity.name} Stent",
            "decision_date": "20240115",
            "decision_description": "Substantially Equivalent",
        }
        return [
            RawSourceRecord(
                source_type=self.source_type,
                jurisdiction=self.jurisdiction,
                url=url,
                title="510k stub",
                payload=payload,
                retrieved_at=datetime.now(UTC),
                content_hash=hash_payload(url, payload, title=identity.name),
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

    real_pipeline_cls = pipeline_mod.DiscoveryPipeline

    def fake_pipeline_factory(*args, **kwargs):
        if "adapters" in kwargs or args:
            return real_pipeline_cls(*args, **kwargs)
        return real_pipeline_cls(adapters=[_FDAStubAdapter()])

    def fake_sessionmaker():
        return Session_

    monkeypatch.setattr(pipeline_mod, "DiscoveryPipeline", fake_pipeline_factory)
    monkeypatch.setattr(pipeline_mod, "get_sessionmaker", fake_sessionmaker)

    app = create_app()
    app.dependency_overrides[get_db] = override_db

    from medfuel.api import routes as routes_mod

    monkeypatch.setattr(routes_mod, "_session", lambda: Session_())

    with TestClient(app) as c:
        yield c


def _submit_and_wait(client: TestClient) -> dict:
    resp = client.post(
        "/v1/regulatory/jobs",
        json={
            "company": {"name": "Example Tx"},
            "scope": {"sources": ["fda"], "jurisdictions": ["US"], "lookback_years": 5},
            "report_plan": {"requested_pages": 6, "max_pages": 10, "english_only": True},
        },
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    status_resp = client.get(f"/v1/regulatory/jobs/{job_id}")
    return status_resp.json()


def test_job_completes_and_produces_report(client):
    body = _submit_and_wait(client)
    assert body["status"].startswith("complete")
    summary = body["result_summary"]
    report_id = summary["report_id"]
    assert report_id and report_id.startswith("rpt_")
    assert summary["events_persisted"] >= 1
    assert summary["claims_persisted"] >= 1


def test_report_endpoints_return_structured_data(client):
    body = _submit_and_wait(client)
    report_id = body["result_summary"]["report_id"]

    rpt_resp = client.get(f"/v1/regulatory/reports/{report_id}")
    assert rpt_resp.status_code == 200
    rpt = rpt_resp.json()
    assert rpt["pages_rendered"] == 6
    assert rpt["adaptive_expansion_triggered"] is False
    assert rpt["confidence_summary"]["high"] + rpt["confidence_summary"]["medium"] >= 1
    assert any(s["slug"] == "executive_summary" for s in rpt["layout_plan"]["sections"])

    narr_resp = client.get(f"/v1/regulatory/reports/{report_id}/narrative")
    assert narr_resp.status_code == 200
    assert "Executive summary" in narr_resp.text

    cite_resp = client.get(f"/v1/regulatory/reports/{report_id}/citations")
    assert cite_resp.status_code == 200
    citations = cite_resp.json()["citations"]
    assert citations and citations[0]["inline_number"] == 1


def test_rerender_creates_new_report_run(client):
    body = _submit_and_wait(client)
    original_id = body["result_summary"]["report_id"]

    rerender = client.post(
        f"/v1/regulatory/reports/{original_id}/rerender",
        json={"requested_pages": 8, "max_pages": 10},
    )
    assert rerender.status_code == 200
    new = rerender.json()
    assert new["report_id"] != original_id
    assert new["pages_requested"] == 8


def test_get_unknown_report_returns_404(client):
    resp = client.get("/v1/regulatory/reports/rpt_does_not_exist")
    assert resp.status_code == 404
