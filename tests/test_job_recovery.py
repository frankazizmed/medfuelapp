from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from medfuel.db.orm import Base
from medfuel.db.registry import DocumentRegistry
from medfuel.models import CompanyIdentity, JurisdictionScope


def _make_job(session, status: str, age_seconds: float) -> str:
    reg = DocumentRegistry(session)
    company = reg.upsert_company(CompanyIdentity(name="Acme"))
    job = reg.create_job(company_id=company.company_id, request_payload={})
    job.status = status
    job.updated_at = datetime.utcnow() - timedelta(seconds=age_seconds)
    session.add(job)
    session.commit()
    return job.job_id


def test_fail_stale_jobs_marks_only_stale_nonterminal(db_session):
    reg = DocumentRegistry(db_session)
    stale_running = _make_job(db_session, "running", age_seconds=1000)
    fresh_running = _make_job(db_session, "running", age_seconds=0)
    stale_complete = _make_job(db_session, "complete", age_seconds=1000)

    failed = reg.fail_stale_jobs(timeout_seconds=300)
    db_session.commit()

    assert failed == [stale_running]
    assert reg.get_job(stale_running).status == "failed"
    assert reg.get_job(stale_running).error
    assert reg.get_job(fresh_running).status == "running"
    assert reg.get_job(stale_complete).status == "complete"


def test_touch_job_resets_the_heartbeat(db_session):
    reg = DocumentRegistry(db_session)
    job_id = _make_job(db_session, "running", age_seconds=1000)
    before = reg.get_job(job_id).updated_at

    reg.touch_job(job_id)
    db_session.commit()

    assert reg.get_job(job_id).updated_at > before
    # Heartbeat makes it fresh again, so the sweep leaves it alone.
    assert reg.fail_stale_jobs(timeout_seconds=300) == []


def test_recover_if_stale_only_fails_old_running_jobs(db_session):
    reg = DocumentRegistry(db_session)
    stale = _make_job(db_session, "running", age_seconds=1000)
    fresh = _make_job(db_session, "running", age_seconds=0)

    assert reg.recover_if_stale(stale, timeout_seconds=300).status == "failed"
    assert reg.recover_if_stale(fresh, timeout_seconds=300).status == "running"
    assert reg.recover_if_stale("job_missing", timeout_seconds=300) is None


@pytest.mark.asyncio
async def test_execute_job_times_out_and_marks_failed(monkeypatch):
    from medfuel.api import routes as routes_mod

    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(routes_mod, "_session", lambda: Session_())

    settings = routes_mod.get_settings()
    monkeypatch.setattr(settings, "job_timeout_seconds", 0.05)

    setup = Session_()
    reg = DocumentRegistry(setup)
    company = reg.upsert_company(CompanyIdentity(name="Acme"))
    job_id = reg.create_job(company_id=company.company_id, request_payload={}).job_id
    setup.commit()
    setup.close()

    async def _hang(**kwargs):
        await asyncio.sleep(5)

    monkeypatch.setattr(routes_mod, "run_discovery", _hang)

    await routes_mod._execute_job(
        identity=CompanyIdentity(name="Acme"),
        scope=JurisdictionScope(),
        requested_pages=4,
        max_pages=8,
        job_id=job_id,
    )

    check = Session_()
    refreshed = DocumentRegistry(check).get_job(job_id)
    assert refreshed.status == "failed"
    assert "timeout" in refreshed.error.lower()
    check.close()
