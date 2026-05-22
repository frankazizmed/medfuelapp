"""Narrative generation layer — Claude turns ranked findings into page text.

Claude only ever sees structured JSON: signal-ranked, verified ClinicalFindings
with citation handles. Never raw study text.
"""
