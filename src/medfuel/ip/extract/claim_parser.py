"""Patent claim parsing and lightweight classification.

Goal: produce structured PatentClaim records the framework scorers
can reason about — independent vs dependent, type (composition,
method, device, etc.), and a rough breadth bucket. This is the
deterministic baseline; an LLM extractor can replace the classifier
later without changing the schema.
"""

from __future__ import annotations

import re

from medfuel.ip.models import ClaimBreadth, ClaimType, PatentClaim

# Composition vs method vs device classification: keyword sets are
# intentionally short — they trigger off the canonical legal phrasings
# rather than trying to do full NLP.
_COMPOSITION_TERMS = (
    "composition", "compound", "antibody", "polynucleotide", "polypeptide",
    "formulation", "salt", "isoform", "molecule", "sequence", "vector",
    "cell line", "construct",
)
_METHOD_TERMS = (
    "method", "process", "treating", "treatment", "administering",
    "diagnosing", "screening",
)
_DEVICE_TERMS = (
    "device", "apparatus", "kit", "assay", "instrument", "implant",
    "catheter", "system comprising",
)
_USE_TERMS = ("use of", "use in")
_SOFTWARE_TERMS = (
    "computer-implemented", "machine learning", "neural network",
    "model trained", "algorithm", "trained model", "processor configured",
)


def _dependency(text: str) -> int | None:
    """Return the parent claim number for a dependent claim, else None.

    Matches forms like "The method of claim 1," or "according to claim 12".
    """
    m = re.search(r"(?:of|according to)\s+claim\s+(\d{1,3})", text, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


_SUBJECT_RE = re.compile(r"^\s*(?:an?|the)\s+([a-zA-Z\-]+)", re.IGNORECASE)


def classify_claim_type(text: str) -> ClaimType:
    t = text.lower()
    subject_match = _SUBJECT_RE.match(text)
    subject = subject_match.group(1).lower() if subject_match else ""

    # The claim's grammatical subject is the strongest signal for type:
    # "A method ..." is a method claim even if it mentions a composition.
    if subject in {"method", "process"}:
        if "computer-implemented" in t or any(s in t for s in _SOFTWARE_TERMS):
            return ClaimType.SOFTWARE
        return ClaimType.METHOD
    if subject in {"composition", "compound", "formulation", "antibody", "polypeptide",
                   "polynucleotide", "molecule", "vector"}:
        return ClaimType.COMPOSITION
    if subject in {"device", "apparatus", "kit", "instrument", "implant", "catheter"}:
        return ClaimType.DEVICE
    if subject == "system":
        return ClaimType.SYSTEM
    if subject == "use":
        return ClaimType.USE

    # Fall back to keyword scan when the subject is generic ("A computer-readable...").
    if any(term in t for term in _SOFTWARE_TERMS):
        return ClaimType.SOFTWARE
    if any(term in t for term in _COMPOSITION_TERMS):
        return ClaimType.COMPOSITION
    if any(term in t for term in _DEVICE_TERMS):
        return ClaimType.DEVICE
    if any(term in t for term in _USE_TERMS):
        return ClaimType.USE
    if any(term in t for term in _METHOD_TERMS):
        return ClaimType.METHOD
    return ClaimType.OTHER


def classify_breadth(text: str) -> ClaimBreadth:
    """Crude breadth heuristic.

    Long claims with many limitations narrow scope; short independent
    claims with broad terms ("comprising", "consisting essentially of")
    skew broad. A real implementation can replace this with model
    scoring; the rest of the pipeline only cares about the bucket.
    """
    wc = len(text.split())
    has_open_transition = "comprising" in text.lower()
    has_closed_transition = "consisting of" in text.lower()
    if has_closed_transition or wc > 220:
        return ClaimBreadth.NARROW
    if has_open_transition and wc < 90:
        return ClaimBreadth.BROAD
    return ClaimBreadth.MODERATE


def parse_claims(raw_claims: list[dict] | None) -> list[PatentClaim]:
    """Normalize a raw claims array into structured PatentClaim records.

    Accepts the PatentsView shape (`claim_text`, `claim_number`,
    `claim_dependent`) and the Google Patents / scraped shape
    (`text`, `number`, `is_independent`).
    """
    if not raw_claims:
        return []
    out: list[PatentClaim] = []
    for raw in raw_claims:
        text = (raw.get("claim_text") or raw.get("text") or "").strip()
        if not text:
            continue
        try:
            number = int(raw.get("claim_number") or raw.get("number") or 0)
        except (TypeError, ValueError):
            number = 0
        if "is_independent" in raw:
            is_independent = bool(raw.get("is_independent"))
        elif "claim_dependent" in raw:
            is_independent = not bool(raw.get("claim_dependent"))
        else:
            is_independent = _dependency(text) is None
        depends = _dependency(text) if not is_independent else None
        out.append(
            PatentClaim(
                claim_number=number,
                text=text,
                is_independent=is_independent,
                claim_type=classify_claim_type(text),
                breadth=classify_breadth(text),
                depends_on=depends,
                word_count=len(text.split()),
                novelty_terms=_novelty_terms(text),
            )
        )
    return out


_NOVELTY_RE = re.compile(
    r"\b(?:wherein|characterized in that|provided that|further comprising)\b",
    re.IGNORECASE,
)


def _novelty_terms(text: str) -> list[str]:
    """Pull short noun-phrase fragments that follow novelty markers.

    These are the bits that typically distinguish an independent claim;
    we surface them so the moat framework can spot composition/process
    novelty without re-parsing the whole claim.
    """
    out: list[str] = []
    for match in _NOVELTY_RE.finditer(text):
        tail = text[match.end():].strip()
        # Take up to the next comma or 12 words, whichever is shorter.
        chunk = tail.split(",")[0]
        chunk_words = chunk.split()[:12]
        if chunk_words:
            out.append(" ".join(chunk_words))
    return out
