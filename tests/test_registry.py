from __future__ import annotations

from datetime import UTC, datetime

from medfuel.db.registry import DocumentRegistry, hash_payload
from medfuel.models.schemas import (
    OFFICIAL_RANK,
    CompanyIdentity,
    RawSourceRecord,
    SourceType,
)


def _record(url: str, payload: dict, title: str = "t") -> RawSourceRecord:
    return RawSourceRecord(
        source_type=SourceType.FDA,
        jurisdiction="US",
        url=url,
        title=title,
        payload=payload,
        retrieved_at=datetime.now(UTC),
        content_hash=hash_payload(url, payload, title=title),
        official_rank=OFFICIAL_RANK[SourceType.FDA],
    )


def test_upsert_company_merges_aliases_and_domains(db_session):
    registry = DocumentRegistry(db_session)
    company = registry.upsert_company(
        CompanyIdentity(name="Example Tx", aliases=["EX"], domains=["example.com"])
    )
    db_session.commit()
    again = registry.upsert_company(
        CompanyIdentity(
            name="Example Tx",
            aliases=["Ex-Tx"],
            domains=["example.com", "investors.example.com"],
            ticker="EXMP",
        )
    )
    db_session.commit()
    assert again.company_id == company.company_id
    assert sorted(again.aliases) == ["EX", "Ex-Tx"]
    assert "investors.example.com" in again.domains
    assert again.ticker == "EXMP"


def test_persist_records_dedupes_on_content_hash(db_session):
    registry = DocumentRegistry(db_session)
    company = registry.upsert_company(CompanyIdentity(name="Example"))
    job = registry.create_job(company.company_id, request_payload={})
    db_session.commit()

    r1 = _record("https://api.fda.gov/x", {"a": 1})
    r2 = _record("https://api.fda.gov/x", {"a": 1})
    r3 = _record("https://api.fda.gov/x", {"a": 2})

    new1, dup1 = registry.persist_records(company.company_id, job.job_id, [r1, r2])
    db_session.commit()
    assert (new1, dup1) == (1, 1)

    new2, dup2 = registry.persist_records(company.company_id, job.job_id, [r3])
    db_session.commit()
    assert (new2, dup2) == (1, 0)


def test_update_job_records_status_transitions(db_session):
    registry = DocumentRegistry(db_session)
    company = registry.upsert_company(CompanyIdentity(name="Example"))
    job = registry.create_job(company.company_id, request_payload={})
    db_session.commit()

    registry.update_job(job.job_id, status="running")
    registry.update_job(
        job.job_id,
        status="complete",
        result_summary={"records_collected": 3},
    )
    db_session.commit()

    fetched = registry.get_job(job.job_id)
    assert fetched is not None
    assert fetched.status == "complete"
    assert fetched.result_summary == {"records_collected": 3}
