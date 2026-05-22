"""Normalize raw document text — strip boilerplate, surface high-signal sections.

Prioritized sections (per spec section 2):
- methods
- inclusion / exclusion criteria
- endpoints
- statistical analysis
- safety / adverse events
- primary outcome reporting
- results tables
"""

from __future__ import annotations

import re

from clinical_evidence.schemas import RawDocument


_HIGH_SIGNAL_HEADINGS = (
    "method",
    "methods",
    "study design",
    "patients and methods",
    "endpoint",
    "endpoints",
    "primary outcome",
    "secondary outcome",
    "primary endpoint",
    "secondary endpoint",
    "statistical analysis",
    "results",
    "efficacy",
    "safety",
    "adverse event",
    "tolerability",
    "discontinuation",
    "inclusion criteria",
    "exclusion criteria",
    "subgroup analysis",
)

_BOILERPLATE_PATTERNS = (
    re.compile(r"©.+?reserved\.?", re.IGNORECASE),
    re.compile(r"all rights reserved", re.IGNORECASE),
    re.compile(r"this article is protected by copyright[^\n]+", re.IGNORECASE),
    re.compile(r"cookies?(?: notice)?[^\n]+", re.IGNORECASE),
    re.compile(r"javascript is disabled[^\n]+", re.IGNORECASE),
)

_HEADING_RE = re.compile(
    r"(?im)^\s*(?P<title>[A-Z][A-Za-z0-9 \-/&,]{2,80})\s*$"
)


def _strip_boilerplate(text: str) -> str:
    for pat in _BOILERPLATE_PATTERNS:
        text = pat.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _segment(text: str) -> list[tuple[str | None, str]]:
    """Split text into (heading, body) tuples using simple heading heuristic."""
    lines = text.splitlines()
    segments: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in lines:
        if _HEADING_RE.match(line) and len(line) < 100:
            segments.append((line.strip(), []))
        else:
            segments[-1][1].append(line)
    return [(h, "\n".join(body).strip()) for h, body in segments if "\n".join(body).strip()]


def _rank(heading: str | None) -> int:
    if not heading:
        return 5
    h = heading.lower()
    for idx, kw in enumerate(_HIGH_SIGNAL_HEADINGS):
        if kw in h:
            return idx
    return len(_HIGH_SIGNAL_HEADINGS) + 5


def normalize(doc: RawDocument) -> RawDocument:
    """Return a copy of the doc with cleaned, high-signal-first ordered text."""
    cleaned = _strip_boilerplate(doc.text)
    segments = _segment(cleaned)
    if not segments:
        return doc.model_copy(update={"text": cleaned})
    segments.sort(key=lambda s: _rank(s[0]))
    rebuilt: list[str] = []
    for heading, body in segments:
        if heading:
            rebuilt.append(f"\n## {heading}\n")
        rebuilt.append(body)
    return doc.model_copy(update={"text": "\n".join(rebuilt).strip()})


def chunk(text: str, *, max_chars: int = 1800, overlap: int = 200) -> list[str]:
    """Conservative chunker for embeddings — paragraph-aware."""
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if len(buf) + len(p) + 2 <= max_chars:
            buf = f"{buf}\n\n{p}".strip()
        else:
            if buf:
                chunks.append(buf)
            if len(p) <= max_chars:
                buf = p
            else:
                for i in range(0, len(p), max_chars - overlap):
                    chunks.append(p[i : i + max_chars])
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks
