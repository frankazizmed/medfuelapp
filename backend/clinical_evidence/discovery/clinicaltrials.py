"""ClinicalTrials.gov v2 API source fetcher.

Docs: https://clinicaltrials.gov/data-api/api
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from clinical_evidence.discovery._http import fetch_json, sha256
from clinical_evidence.schemas import (
    CompanyContext,
    DiscoveryResult,
    RawDocument,
    SourceKind,
    Trial,
    TrialPhase,
)

log = logging.getLogger(__name__)

_BASE = "https://clinicaltrials.gov/api/v2/studies"

_PHASE_MAP = {
    "EARLY_PHASE1": TrialPhase.phase1,
    "PHASE1": TrialPhase.phase1,
    "PHASE1/PHASE2": TrialPhase.phase1_2,
    "PHASE2": TrialPhase.phase2,
    "PHASE2/PHASE3": TrialPhase.phase2_3,
    "PHASE3": TrialPhase.phase3,
    "PHASE4": TrialPhase.phase4,
}


def _phase(raw: list[str] | None) -> TrialPhase:
    if not raw:
        return TrialPhase.unknown
    return _PHASE_MAP.get(raw[0], TrialPhase.unknown)


async def fetch(company: CompanyContext) -> DiscoveryResult:
    """Search ClinicalTrials.gov by sponsor + asset names; return trials + docs."""

    queries: list[str] = []
    queries.append(company.name)
    for asset in company.assets:
        queries.append(asset)

    trials: list[Trial] = []
    docs: list[RawDocument] = []
    seen_nct: set[str] = set()
    now = datetime.now(timezone.utc)

    for q in queries:
        try:
            data = await fetch_json(
                _BASE,
                params={
                    "query.term": q,
                    "pageSize": 50,
                    "format": "json",
                },
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("ClinicalTrials.gov fetch failed for %r: %s", q, exc)
            continue

        for study in (data or {}).get("studies", []):
            ident = study.get("protocolSection", {}).get("identificationModule", {})
            design = study.get("protocolSection", {}).get("designModule", {})
            status_mod = study.get("protocolSection", {}).get("statusModule", {})
            outcomes = study.get("protocolSection", {}).get("outcomesModule", {})
            cond_mod = study.get("protocolSection", {}).get("conditionsModule", {})
            nct = ident.get("nctId")
            if not nct or nct in seen_nct:
                continue
            seen_nct.add(nct)

            text = json.dumps(study, indent=2)
            doc = RawDocument(
                doc_id=f"ct-{nct}",
                company_id=company.company_id,
                source=SourceKind.clinicaltrials,
                url=f"https://clinicaltrials.gov/study/{nct}",
                title=ident.get("briefTitle"),
                fetched_at=now,
                text=text,
                metadata={"query": q},
                sha256=sha256(text),
            )
            docs.append(doc)

            design_info = design.get("designInfo", {}) or {}
            interventional = (design.get("studyType") == "INTERVENTIONAL")
            randomized = None
            blinded = None
            placebo = None
            if interventional:
                allocation = (design_info.get("allocation") or "").upper()
                masking = (design_info.get("maskingInfo", {}) or {}).get("masking", "").upper()
                randomized = allocation == "RANDOMIZED"
                blinded = masking not in ("", "NONE", "OPEN")
                interv_model = (design_info.get("interventionModel") or "").upper()
                placebo = "PLACEBO" in interv_model

            primary = [o.get("measure", "") for o in outcomes.get("primaryOutcomes", []) or []]
            secondary = [o.get("measure", "") for o in outcomes.get("secondaryOutcomes", []) or []]

            trials.append(
                Trial(
                    trial_id=f"tr-{nct}",
                    company_id=company.company_id,
                    nct_id=nct,
                    title=ident.get("briefTitle"),
                    phase=_phase(design.get("phases")),
                    indication=(cond_mod.get("conditions") or [None])[0],
                    enrollment=(design.get("enrollmentInfo", {}) or {}).get("count"),
                    randomized=randomized,
                    blinded=blinded,
                    placebo_controlled=placebo,
                    primary_endpoints=[p for p in primary if p],
                    secondary_endpoints=[s for s in secondary if s],
                    status=status_mod.get("overallStatus"),
                    start_date=(status_mod.get("startDateStruct", {}) or {}).get("date"),
                    primary_completion_date=(
                        status_mod.get("primaryCompletionDateStruct", {}) or {}
                    ).get("date"),
                    source_doc_ids=[doc.doc_id],
                )
            )

    log.info("ClinicalTrials.gov returned %d trials for %s", len(trials), company.name)
    return DiscoveryResult(trials=trials, documents=docs)
