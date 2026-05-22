"""Compute the 9 institutional signal dimensions per ClinicalFinding."""

from __future__ import annotations

import logging

from clinical_evidence.schemas import ClinicalFinding, SignalScores, Trial
from clinical_evidence.signal import rules

log = logging.getLogger(__name__)


def score_findings(
    findings: list[ClinicalFinding],
    *,
    trials: list[Trial],
) -> list[ClinicalFinding]:
    """Return findings annotated with deterministic SignalScores + risk flags.

    A separate LLM judge step (handled in narrative/generator if needed) can
    refine the ambiguous dimensions (differentiation, physician_relevance)
    using small Claude calls. The deterministic floor is auditable.
    """

    trial_index = {t.trial_id: t for t in trials}
    out: list[ClinicalFinding] = []
    for f in findings:
        trial = trial_index.get(f.trial_id) if f.trial_id else None
        scores = SignalScores(
            evidence_strength=rules.evidence_strength(f, trial),
            endpoint_quality=rules.endpoint_quality(f),
            statistical_robustness=rules.statistical_robustness(f),
            physician_relevance=rules.physician_relevance(f),
            commercialization_relevance=rules.commercialization_relevance(f),
            differentiation=rules.differentiation(f),
            safety_concern=rules.safety_concern(f),
            regulatory_relevance=rules.regulatory_relevance(f, trial),
            durability=rules.durability(f),
        )
        risks = rules.detect_risks(f, trial)
        updated_endpoint_type = (
            f.endpoint_type
            if f.endpoint_type and f.endpoint_type != "unknown"
            else rules.classify_endpoint(f.endpoint)
        )
        out.append(
            f.model_copy(
                update={
                    "scores": scores,
                    "risk_flags": risks,
                    "endpoint_type": updated_endpoint_type,
                }
            )
        )
    log.info("Scored %d findings", len(out))
    return out
