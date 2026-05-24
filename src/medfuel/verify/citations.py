from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from medfuel.db.orm import CitationRow, SourceDocumentRow
from medfuel.models import Confidence, VerifiedClaim


@dataclass
class CitationEntry:
    inline_number: int
    claim_id: str | None
    source_doc_id: str
    url: str
    locator: str | None
    source_confidence: str


def build_citation_table(
    *,
    session: Session,
    report_id: str,
    claims: list[VerifiedClaim],
) -> tuple[list[CitationEntry], dict[str, list[int]]]:
    """Assign stable inline citation numbers per (claim, source_doc) pair.

    Returns the ordered citation table plus a per-claim mapping of inline
    numbers so the narrative renderer can append `[n]` tags deterministically.
    Citations are persisted via CitationRow keyed to the report run.
    """
    inline_lookup: dict[str, int] = {}
    citations: list[CitationEntry] = []
    per_claim: dict[str, list[int]] = {}
    next_number = 1

    doc_ids = sorted({sid for c in claims for sid in c.source_doc_ids})
    doc_rows = (
        session.query(SourceDocumentRow)
        .filter(SourceDocumentRow.source_doc_id.in_(doc_ids))
        .all()
        if doc_ids
        else []
    )
    docs = {d.source_doc_id: d for d in doc_rows}

    for claim in claims:
        nums: list[int] = []
        for sid in claim.source_doc_ids:
            doc = docs.get(sid)
            if doc is None:
                continue
            if sid in inline_lookup:
                nums.append(inline_lookup[sid])
                continue
            num = next_number
            next_number += 1
            inline_lookup[sid] = num
            entry = CitationEntry(
                inline_number=num,
                claim_id=claim.claim_id,
                source_doc_id=sid,
                url=doc.url,
                locator=doc.page_locator,
                source_confidence=_confidence_label(claim.confidence),
            )
            citations.append(entry)
            session.add(
                CitationRow(
                    citation_id=f"cit_{uuid.uuid4().hex[:12]}",
                    report_id=report_id,
                    claim_id=claim.claim_id,
                    inline_number=num,
                    source_doc_id=sid,
                    url=doc.url,
                    locator=doc.page_locator,
                    source_confidence=entry.source_confidence,
                )
            )
            nums.append(num)
        per_claim[claim.claim_id] = nums
    session.flush()
    return citations, per_claim


def _confidence_label(confidence: Confidence) -> str:
    return confidence.value
