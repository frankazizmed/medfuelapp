"""OpenAI structured-output client used by the extraction layer.

The actual model name is configurable via CE_EXTRACTION_MODEL. Spec calls
for a small OpenAI model (named "GPT-5.5 mini" at the time of writing);
pin this to whatever the current best small-and-cheap structured-output
model is at deploy time.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from clinical_evidence.config import get_settings
from clinical_evidence.schemas import (
    ClinicalFinding,
    EndpointType,
    FindingType,
    SignalScores,
    StatisticalResult,
    VerificationStatus,
)

log = logging.getLogger(__name__)


class ExtractedFinding(BaseModel):
    """Schema the LLM is asked to fill — narrower than ClinicalFinding."""

    finding_type: FindingType
    description: str
    endpoint: str | None = None
    endpoint_type: EndpointType = EndpointType.unknown
    measure: str | None = None
    value: float | None = None
    units: str | None = None
    p_value: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    n: int | None = None
    follow_up_months: float | None = None
    raw_excerpt: str | None = None


class ExtractionEnvelope(BaseModel):
    findings: list[ExtractedFinding] = Field(default_factory=list)


def _client():
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:  # pragma: no cover
        log.warning("openai not installed; extraction will return empty.")
        return None
    return OpenAI(api_key=settings.openai_api_key)


async def extract_from_text(
    *,
    text: str,
    source: str,
    title: str | None,
    url: str,
    company_id: str,
    source_doc_id: str,
    trial_id: str | None = None,
    pub_id: str | None = None,
) -> list[ClinicalFinding]:
    """Call the structured-output API and map results to ClinicalFinding[]."""

    settings = get_settings()
    client = _client()
    if client is None:
        log.info("OpenAI client unavailable; returning no findings.")
        return []

    from clinical_evidence.extraction.prompts import EXTRACT_SYSTEM, EXTRACT_USER_TEMPLATE

    user = EXTRACT_USER_TEMPLATE.format(
        source=source, title=title or "(none)", url=url, text=text[:18000]
    )

    try:
        resp = client.chat.completions.create(
            model=settings.extraction_model,
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": user},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "ExtractionEnvelope",
                    "schema": ExtractionEnvelope.model_json_schema(),
                    "strict": True,
                },
            },
            temperature=0,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("OpenAI extraction call failed: %s", exc)
        return []

    raw = resp.choices[0].message.content
    if not raw:
        return []
    try:
        envelope = ExtractionEnvelope.model_validate_json(raw)
    except Exception as exc:  # noqa: BLE001
        log.warning("Extraction envelope failed to parse: %s", exc)
        return []

    return [_to_finding(f, company_id, source_doc_id, trial_id, pub_id) for f in envelope.findings]


def _to_finding(
    f: ExtractedFinding,
    company_id: str,
    source_doc_id: str,
    trial_id: str | None,
    pub_id: str | None,
) -> ClinicalFinding:
    import uuid

    result = None
    if any(v is not None for v in (f.measure, f.value, f.p_value, f.ci_low, f.ci_high, f.n)):
        result = StatisticalResult(
            measure=f.measure,
            value=f.value,
            units=f.units,
            p_value=f.p_value,
            ci_low=f.ci_low,
            ci_high=f.ci_high,
            n=f.n,
        )
    return ClinicalFinding(
        finding_id=f"f-{uuid.uuid4().hex[:12]}",
        company_id=company_id,
        trial_id=trial_id,
        pub_id=pub_id,
        source_doc_id=source_doc_id,
        finding_type=f.finding_type,
        endpoint=f.endpoint,
        endpoint_type=f.endpoint_type,
        description=f.description,
        result=result,
        follow_up_months=f.follow_up_months,
        verification_status=VerificationStatus.REPORTED,
        scores=SignalScores(),
        risk_flags=[],
        raw_excerpt=f.raw_excerpt,
    )


def stub_extract(
    *,
    text: str,
    source: str,
    title: str | None,
    url: str,
    company_id: str,
    source_doc_id: str,
    trial_id: str | None = None,
    pub_id: str | None = None,
) -> list[ClinicalFinding]:
    """Deterministic fallback when no API key is present.

    Used by tests and offline harness runs so the pipeline can still produce
    structured output without a network round-trip. Only fires when text
    contains obvious efficacy/safety keywords.
    """
    import re
    import uuid

    findings: list[ClinicalFinding] = []
    lower = text.lower()
    if not any(k in lower for k in ("primary endpoint", "p =", "p<", "p =", "hazard ratio", "adverse event")):
        return findings

    p_match = re.search(r"p\s*[=<>]\s*([0-9.]+)", lower)
    n_match = re.search(r"n\s*=\s*([0-9,]+)", lower)
    pval = float(p_match.group(1)) if p_match else None
    nval = int(n_match.group(1).replace(",", "")) if n_match else None

    findings.append(
        ClinicalFinding(
            finding_id=f"f-{uuid.uuid4().hex[:12]}",
            company_id=company_id,
            trial_id=trial_id,
            pub_id=pub_id,
            source_doc_id=source_doc_id,
            finding_type=FindingType.efficacy,
            endpoint="primary endpoint",
            endpoint_type=EndpointType.unknown,
            description=text[:280].strip(),
            result=StatisticalResult(p_value=pval, n=nval) if (pval or nval) else None,
            verification_status=VerificationStatus.REPORTED,
            scores=SignalScores(),
            risk_flags=[],
            raw_excerpt=text[:180].strip(),
        )
    )
    return findings
