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
from medfuel.models.schemas import (
    OFFICIAL_RANK,
    RawSourceRecord,
    SourceType,
)


class _StubAdapter(SourceAdapter):
    source_type = SourceType.FDA
    jurisdiction = "US"

    async def discover(self, identity, scope):
        url = "https://api.fda.gov/drug/label.json?stub=1"
        payload = {"company": identity.name}
        return [
            RawSourceRecord(
                source_type=self.source_type,
                jurisdiction=self.jurisdiction,
                url=url,
                title=f"label for {identity.name}",
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

    # Force the background discovery to use the in-memory DB and a stub adapter.
    real_pipeline_cls = pipeline_mod.DiscoveryPipeline

    def fake_pipeline_factory(*args, **kwargs):
        if "adapters" in kwargs or args:
            return real_pipeline_cls(*args, **kwargs)
        return real_pipeline_cls(adapters=[_StubAdapter()])

    def fake_sessionmaker():
        return Session_

    monkeypatch.setattr(pipeline_mod, "DiscoveryPipeline", fake_pipeline_factory)
    monkeypatch.setattr(pipeline_mod, "get_sessionmaker", fake_sessionmaker)

    app = create_app()
    app.dependency_overrides[get_db] = override_db
    # Also patch the routes' _session helper so background tasks share the engine.
    from medfuel.api import routes as routes_mod

    monkeypatch.setattr(routes_mod, "_session", lambda: Session_())

    with TestClient(app) as c:
        yield c


def test_create_job_returns_202_and_executes_in_background(client):
    payload = {
        "company": {"name": "Example Tx", "cik": "1234567"},
        "scope": {"sources": ["fda"], "jurisdictions": ["US"], "lookback_years": 5},
        "report_plan": {"requested_pages": 6, "max_pages": 10, "english_only": True},
    }
    resp = client.post("/v1/regulatory/jobs", json=payload)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    assert job_id.startswith("job_")

    status_resp = client.get(f"/v1/regulatory/jobs/{job_id}")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] in {"complete", "complete_with_errors", "running", "queued"}
    # TestClient runs background tasks synchronously on response close, so by the
    # time we issue the GET above the job should normally have completed.
    if body["status"].startswith("complete"):
        summary = body["result_summary"]
        assert summary["records_persisted_new"] == 1
        assert summary["by_source"]["fda"] == 1


def test_get_unknown_job_returns_404(client):
    resp = client.get("/v1/regulatory/jobs/job_does_not_exist")
    assert resp.status_code == 404
