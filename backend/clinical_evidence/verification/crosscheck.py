"""Cross-source verification.

Goal: for each ClinicalFinding, determine whether the same claim appears in
≥2 independent sources (VERIFIED), one primary source (REPORTED), or
nowhere directly (INFERRED).
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

from clinical_evidence.schemas import (
    ClinicalFinding,
    Publication,
    RawDocument,
    Trial,
    VerificationStatus,
)

log = logging.getLogger(__name__)


def _normalize_key(finding: ClinicalFinding) -> str:
    """Hash an endpoint + result quartile so the same claim collides across sources."""

    endpoint = (finding.endpoint or finding.finding_type).lower().strip()
    endpoint = re.sub(r"[^a-z0-9]+", " ", endpoint)
    value_bucket = "x"
    if finding.result and finding.result.value is not None:
        v = finding.result.value
        # bucket to nearest 5% to allow rounding noise across sources
        value_bucket = f"{round(v / 5) * 5}"
    return f"{finding.finding_type}::{endpoint}::{value_bucket}"


def reconcile(
    findings: list[ClinicalFinding],
    *,
    documents: list[RawDocument],
    trials: list[Trial],
    publications: list[Publication],
) -> list[ClinicalFinding]:
    """Tag each finding with a verification status based on cross-source agreement."""

    doc_source_by_id = {d.doc_id: d.source for d in documents}

    # Group findings by claim key, tracking distinct source kinds per claim
    sources_by_key: dict[str, set[str]] = defaultdict(set)
    for f in findings:
        key = _normalize_key(f)
        src = doc_source_by_id.get(f.source_doc_id)
        if src is not None:
            sources_by_key[key].add(str(src.value if hasattr(src, "value") else src))

    out: list[ClinicalFinding] = []
    for f in findings:
        key = _normalize_key(f)
        independent_sources = sources_by_key.get(key, set())
        if len(independent_sources) >= 2:
            status = VerificationStatus.VERIFIED
        else:
            status = VerificationStatus.REPORTED
        out.append(f.model_copy(update={"verification_status": status}))

    log.info(
        "Verification: %d/%d findings VERIFIED across ≥2 sources",
        sum(1 for f in out if f.verification_status == VerificationStatus.VERIFIED.value),
        len(out),
    )
    return out
