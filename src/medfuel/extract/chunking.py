from __future__ import annotations

from dataclasses import dataclass

from medfuel.config import get_settings
from medfuel.extract.redaction import redact
from medfuel.models import RawSourceRecord, SourceType

# Source types whose payloads are unstructured enough to warrant chunking
# and embedding. Structured regulator records (FDA, SEC, CT.gov, EMA, USPTO,
# PubMed) are handled by the rule extractor and don't need chunks.
UNSTRUCTURED_SOURCE_TYPES: set[SourceType] = {
    SourceType.MHRA,
    SourceType.PMDA,
    SourceType.COMPANY,
    SourceType.INVESTOR_DECK,
}


@dataclass
class Chunk:
    chunk_index: int
    char_start: int
    char_end: int
    text: str
    redaction_count: int


def extract_text(record: RawSourceRecord) -> str:
    """Best-effort flatten of a record's payload into a text blob for chunking.

    Real Phase-2-future implementations would route through Firecrawl
    `/v2/parse` (returns markdown + reading order) for PDFs and scans; this
    fallback is enough for HTML markdown payloads and free-form fields.
    """
    payload = record.payload or {}
    for key in ("markdown", "content", "content_snippet", "text", "summary"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    # As a last resort, stitch together title + URL + a flat dump of keys.
    parts: list[str] = [record.title or "", str(record.url)]
    for k, v in payload.items():
        if isinstance(v, str) and v.strip():
            parts.append(f"{k}: {v}")
    return "\n".join(parts).strip()


def chunk_text(
    text: str,
    *,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[Chunk]:
    """Sliding-window chunker.

    Defaults are pulled from settings so a deployment can tune chunk size
    without touching code. Each chunk preserves its original (char_start,
    char_end) offsets so citation locators downstream stay precise.
    """
    settings = get_settings()
    size = chunk_size or settings.chunk_char_size
    step_overlap = overlap if overlap is not None else settings.chunk_char_overlap
    if size <= 0:
        return []
    if step_overlap >= size:
        step_overlap = max(0, size // 4)

    chunks: list[Chunk] = []
    if not text:
        return chunks

    i = 0
    idx = 0
    stride = size - step_overlap
    while i < len(text):
        end = min(i + size, len(text))
        slice_text = text[i:end]
        redacted = redact(slice_text)
        chunks.append(
            Chunk(
                chunk_index=idx,
                char_start=i,
                char_end=end,
                text=redacted.text,
                redaction_count=redacted.total,
            )
        )
        idx += 1
        if end == len(text):
            break
        i += stride
    return chunks
