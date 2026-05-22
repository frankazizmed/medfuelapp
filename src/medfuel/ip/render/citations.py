"""IP citations engine.

Mirrors medfuel.verify.citations but persists into ip_citations and is
keyed by IPFinding instead of VerifiedClaim.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from medfuel.db.orm import SourceDocumentRow
from medfuel.ip.db_orm import IPCitationRow
from medfuel.ip.models import IPConfidence, IPFinding


@dataclass
class IPCitationEntry:
    inline_number: int
    finding_id: str | None
    source_doc_id: str
    url: str
    locator: str | None
    source_confidence: str
    evidence_kind: str


def build_ip_citation_table(
    *,
    session: Session,
    report_id: str,
    findings: list[IPFinding],
) -> tuple[list[IPCitationEntry], dict[str, list[int]]]:
    inline_lookup: dict[str, int] = {}
    citations: list[IPCitationEntry] = []
    per_finding: dict[str, list[int]] = {}
    next_number = 1

    doc_ids = sorted({sid for f in findings for sid in f.source_doc_ids})
    doc_rows = (
        session.query(SourceDocumentRow)
        .filter(SourceDocumentRow.source_doc_id.in_(doc_ids))
        .all()
        if doc_ids
        else []
    )
    docs = {d.source_doc_id: d for d in doc_rows}

    for finding in findings:
        nums: list[int] = []
        for sid in finding.source_doc_ids:
            doc = docs.get(sid)
            if doc is None:
                continue
            if sid in inline_lookup:
                nums.append(inline_lookup[sid])
                continue
            num = next_number
            next_number += 1
            inline_lookup[sid] = num
            entry = IPCitationEntry(
                inline_number=num,
                finding_id=finding.finding_id,
                source_doc_id=sid,
                url=doc.url,
                locator=doc.page_locator,
                source_confidence=_confidence_label(finding.confidence),
                evidence_kind=_evidence_kind(doc.source_type),
            )
            citations.append(entry)
            session.add(
                IPCitationRow(
                    citation_id=f"ipc_{uuid.uuid4().hex[:12]}",
                    report_id=report_id,
                    finding_id=finding.finding_id,
                    inline_number=num,
                    source_doc_id=sid,
                    url=doc.url,
                    locator=doc.page_locator,
                    source_confidence=entry.source_confidence,
                    evidence_kind=entry.evidence_kind,
                )
            )
            nums.append(num)
        per_finding[finding.finding_id] = nums
    session.flush()
    return citations, per_finding


def _confidence_label(confidence: IPConfidence) -> str:
    return confidence.value


def _evidence_kind(source_type: str) -> str:
    if source_type in {"ptab", "litigation"}:
        return "tribunal"
    if source_type in {"uspto_assignment"}:
        return "assignment"
    if source_type in {"sec", "sec_ip"}:
        return "sec_filing"
    return "patent"
