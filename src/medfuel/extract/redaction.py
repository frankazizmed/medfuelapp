from __future__ import annotations

import re
from dataclasses import dataclass

# Defensive PII/PHI redaction for unstructured chunks before they reach the
# embedding model or the LLM extractor. This is intentionally narrow: it is a
# placeholder for a real HIPAA-compliant pipeline (Safe Harbor or Expert
# Determination per HHS guidance), not a substitute. Production deployments
# that accept user-uploaded clinical or PHI-bearing material must replace
# this with a vetted de-identification step.
_PATTERNS: dict[str, re.Pattern[str]] = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "phone": re.compile(
        r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    ),
    "mrn": re.compile(r"\bMRN[:\s#]*\d{4,}\b", re.IGNORECASE),
    "dob": re.compile(
        r"\b(?:DOB|date of birth)[:\s]*\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b",
        re.IGNORECASE,
    ),
    "credit_card": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
}


@dataclass
class RedactionResult:
    text: str
    counts: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def redact(text: str) -> RedactionResult:
    if not text:
        return RedactionResult(text="", counts={})
    counts: dict[str, int] = {}
    out = text
    for label, pattern in _PATTERNS.items():
        matches = pattern.findall(out)
        if not matches:
            continue
        counts[label] = len(matches)
        out = pattern.sub(f"[REDACTED:{label}]", out)
    return RedactionResult(text=out, counts=counts)
