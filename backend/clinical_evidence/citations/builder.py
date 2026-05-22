"""Build the numbered citation list from the findings and source documents."""

from __future__ import annotations

from clinical_evidence.schemas import (
    Citation,
    ClinicalFinding,
    RawDocument,
    SignalScores,
    SourceKind,
)
from clinical_evidence.verification.confidence import confidence_for


def build(
    *,
    findings: list[ClinicalFinding],
    documents: list[RawDocument],
) -> list[Citation]:
    """Assign each cited document a stable citation number in score-rank order.

    A document is cited if at least one finding's source_doc_id points to it.
    Numbers are assigned in descending finding composite-score order so the
    most-relied-upon sources get the lowest numbers.
    """

    doc_index = {d.doc_id: d for d in documents}

    # Aggregate per-doc evidence weight from the findings that cite it.
    doc_weights: dict[str, float] = {}
    doc_best_finding: dict[str, ClinicalFinding] = {}
    for f in findings:
        if f.source_doc_id not in doc_index:
            continue
        s = f.scores if isinstance(f.scores, SignalScores) else SignalScores(**f.scores)
        composite = s.composite()
        doc_weights[f.source_doc_id] = doc_weights.get(f.source_doc_id, 0.0) + composite
        prev = doc_best_finding.get(f.source_doc_id)
        if prev is None or composite > (
            (prev.scores if isinstance(prev.scores, SignalScores) else SignalScores(**prev.scores)).composite()
        ):
            doc_best_finding[f.source_doc_id] = f

    # Rank documents by weight (descending) for citation number assignment.
    ordered_doc_ids = sorted(doc_weights.keys(), key=lambda d: doc_weights[d], reverse=True)

    citations: list[Citation] = []
    for i, doc_id in enumerate(ordered_doc_ids, start=1):
        doc = doc_index[doc_id]
        best = doc_best_finding[doc_id]
        source = doc.source if isinstance(doc.source, SourceKind) else SourceKind(doc.source)
        conf = confidence_for(best, source)
        s = best.scores if isinstance(best.scores, SignalScores) else SignalScores(**best.scores)
        citations.append(
            Citation(
                number=i,
                doc_id=doc.doc_id,
                url=doc.url,
                title=doc.title,
                source=source,
                confidence=conf,
                evidence_strength=round(s.evidence_strength, 3),
            )
        )
    return citations
