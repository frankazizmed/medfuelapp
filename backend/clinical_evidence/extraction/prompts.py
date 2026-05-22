"""Per-doc-type extraction prompts.

Each prompt is intentionally narrow: it asks for a list of ClinicalFinding
objects with the exact fields our Pydantic schema expects. The structured
output API enforces shape; the prompt enforces relevance.
"""

EXTRACT_SYSTEM = """You extract clinical evidence from biomedical source documents for an
institutional life-sciences diligence platform. You output only structured
findings that materially affect interpretation of efficacy, safety, design,
durability, regulatory progress, or commercial potential.

Strict rules:
- One finding per atomic claim.
- Quote a short raw_excerpt verbatim when possible (≤180 chars).
- If a number, p-value, CI, or N is stated, capture it.
- finding_type must be one of: efficacy, safety, design, durability, subgroup,
  regulatory, pharmacology, comparator.
- endpoint_type must be one of: hard, surrogate, composite, unknown.
- Do not infer. Do not editorialize. Do not include mechanism descriptions.
- Skip generic disease background. Skip management optimism. Skip generic MOA.
- If no clinical evidence is present, return an empty list.
"""

EXTRACT_USER_TEMPLATE = """SOURCE: {source}
TITLE: {title}
URL: {url}

TEXT:
{text}

Return JSON conforming to the provided schema.
"""
