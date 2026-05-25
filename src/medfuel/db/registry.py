from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from medfuel.db.orm import AuditEvent, CompanyRow, JobRow, SourceDocumentRow
from medfuel.models.schemas import CompanyIdentity, RawSourceRecord

# A job in one of these states has reached a final outcome and must never be
# revived by the stale-job recovery sweep.
TERMINAL_JOB_STATUSES = frozenset({"complete", "complete_with_errors", "failed"})

_STALE_JOB_ERROR = (
    "Job made no progress within the configured timeout; the worker likely "
    "terminated mid-run (crash, deploy, or hung request)."
)


def hash_payload(url: str, payload: dict | None, title: str | None = None) -> str:
    """Stable content hash for dedupe. Deterministic key order."""
    body = json.dumps(payload or {}, sort_keys=True, default=str)
    digest = hashlib.sha256()
    digest.update(url.encode("utf-8"))
    digest.update(b"\x00")
    if title:
        digest.update(title.encode("utf-8"))
        digest.update(b"\x00")
    digest.update(body.encode("utf-8"))
    return digest.hexdigest()


class DocumentRegistry:
    """Provenance-first persistence for raw source records.

    Treats documents as immutable: duplicate (company_id, content_hash) pairs are
    skipped rather than overwritten. An audit event is emitted on every insert and
    duplicate-collision so the collection layer is fully traceable.
    """

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------ companies
    def upsert_company(self, identity: CompanyIdentity) -> CompanyRow:
        existing: CompanyRow | None = None
        if identity.cik:
            stmt = select(CompanyRow).where(CompanyRow.cik == identity.canonical_cik())
            existing = self.session.execute(stmt).scalar_one_or_none()
        if existing is None:
            stmt = select(CompanyRow).where(CompanyRow.legal_name == identity.name)
            existing = self.session.execute(stmt).scalar_one_or_none()

        if existing is not None:
            existing.aliases = sorted(set(existing.aliases or []) | set(identity.aliases))
            existing.domains = sorted(set(existing.domains or []) | set(identity.domains))
            if identity.ticker and not existing.ticker:
                existing.ticker = identity.ticker
            if identity.cik and not existing.cik:
                existing.cik = identity.canonical_cik()
            self.session.add(existing)
            self.session.flush()
            return existing

        row = CompanyRow(
            company_id=f"cmp_{uuid.uuid4().hex[:12]}",
            legal_name=identity.name,
            aliases=identity.aliases,
            ticker=identity.ticker,
            cik=identity.canonical_cik(),
            domains=identity.domains,
        )
        self.session.add(row)
        self.session.flush()
        self._audit("company", row.company_id, "insert", after_hash=None)
        return row

    # ----------------------------------------------------------------------- jobs
    def create_job(
        self,
        company_id: str,
        request_payload: dict,
        requested_pages: int = 4,
    ) -> JobRow:
        row = JobRow(
            job_id=f"job_{uuid.uuid4().hex[:12]}",
            company_id=company_id,
            request_payload=request_payload,
            requested_pages=requested_pages,
        )
        self.session.add(row)
        self.session.flush()
        self._audit("job", row.job_id, "insert")
        return row

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        result_summary: dict | None = None,
        error: str | None = None,
    ) -> JobRow:
        row = self.session.get(JobRow, job_id)
        if row is None:
            raise KeyError(f"Job not found: {job_id}")
        if status is not None:
            row.status = status
        if result_summary is not None:
            row.result_summary = result_summary
        if error is not None:
            row.error = error
        row.updated_at = datetime.utcnow()
        self.session.add(row)
        self.session.flush()
        self._audit("job", row.job_id, f"update:{status or 'meta'}")
        return row

    def get_job(self, job_id: str) -> JobRow | None:
        return self.session.get(JobRow, job_id)

    def touch_job(self, job_id: str) -> None:
        """Heartbeat: bump updated_at so progress resets the no-progress clock.

        Called at each pipeline stage so a long-but-healthy run is never mistaken
        for a dead one. Flushes within the caller's transaction; the caller commits.
        """
        row = self.session.get(JobRow, job_id)
        if row is None:
            return
        row.updated_at = datetime.utcnow()
        self.session.add(row)
        self.session.flush()

    def recover_if_stale(
        self,
        job_id: str,
        *,
        timeout_seconds: float,
        reason: str = _STALE_JOB_ERROR,
    ) -> JobRow | None:
        """Force-fail a single non-terminal job whose last heartbeat is too old.

        Returns the (possibly updated) row, or None if the job doesn't exist. Used
        on status polls so a stuck job surfaces as "failed" instead of spinning.
        """
        row = self.session.get(JobRow, job_id)
        if row is None:
            return None
        cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds)
        if row.status not in TERMINAL_JOB_STATUSES and row.updated_at < cutoff:
            row.status = "failed"
            row.error = reason
            row.updated_at = datetime.utcnow()
            self.session.add(row)
            self.session.flush()
            self._audit("job", row.job_id, "update:failed", detail={"reason": "stale_timeout"})
        return row

    def fail_stale_jobs(
        self,
        *,
        timeout_seconds: float,
        reason: str = _STALE_JOB_ERROR,
    ) -> list[str]:
        """Force-fail every non-terminal job with a stale heartbeat. Returns their ids.

        Run at startup to reclaim jobs orphaned by the previous process. Staleness
        (not just "running") is the gate, so a job actively heartbeating elsewhere
        is left untouched.
        """
        cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds)
        stmt = select(JobRow).where(
            JobRow.status.not_in(TERMINAL_JOB_STATUSES),
            JobRow.updated_at < cutoff,
        )
        stale = list(self.session.execute(stmt).scalars())
        for row in stale:
            row.status = "failed"
            row.error = reason
            row.updated_at = datetime.utcnow()
            self.session.add(row)
            self._audit("job", row.job_id, "update:failed", detail={"reason": "stale_timeout"})
        if stale:
            self.session.flush()
        return [row.job_id for row in stale]

    # ------------------------------------------------------------- source records
    def persist_records(
        self,
        company_id: str,
        job_id: str | None,
        records: Iterable[RawSourceRecord],
    ) -> tuple[int, int]:
        new_count = 0
        dup_count = 0
        for rec in records:
            stmt = select(SourceDocumentRow).where(
                SourceDocumentRow.company_id == company_id,
                SourceDocumentRow.content_hash == rec.content_hash,
            )
            existing = self.session.execute(stmt).scalar_one_or_none()
            if existing is not None:
                dup_count += 1
                self._audit(
                    "source_document",
                    existing.source_doc_id,
                    "duplicate_skip",
                    after_hash=rec.content_hash,
                )
                continue

            row = SourceDocumentRow(
                source_doc_id=f"src_{uuid.uuid4().hex[:12]}",
                company_id=company_id,
                job_id=job_id,
                source_type=rec.source_type.value,
                jurisdiction=rec.jurisdiction,
                url=str(rec.url),
                title=rec.title,
                payload=rec.payload,
                published_at=rec.published_at,
                retrieved_at=rec.retrieved_at,
                page_locator=rec.page_locator,
                external_id=rec.external_id,
                content_hash=rec.content_hash,
                official_rank=rec.official_rank,
            )
            self.session.add(row)
            self.session.flush()
            self._audit(
                "source_document",
                row.source_doc_id,
                "insert",
                after_hash=row.content_hash,
            )
            new_count += 1
        return new_count, dup_count

    # ---------------------------------------------------------------------- audit
    def _audit(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        *,
        before_hash: str | None = None,
        after_hash: str | None = None,
        detail: dict | None = None,
    ) -> None:
        self.session.add(
            AuditEvent(
                audit_id=f"aud_{uuid.uuid4().hex[:12]}",
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                before_hash=before_hash,
                after_hash=after_hash,
                detail=detail,
            )
        )
