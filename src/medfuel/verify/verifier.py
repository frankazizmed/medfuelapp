from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from medfuel.db.orm import (
    AssetRow,
    ClaimRow,
    RegulatoryEventRow,
    SourceDocumentRow,
)
from medfuel.extract.dedupe import dedupe_events, event_key
from medfuel.extract.normalize import resolve_asset
from medfuel.models import (
    CandidateEvent,
    Confidence,
    RegulatoryEvent,
    VerificationState,
    VerifiedClaim,
)
from medfuel.score.signal import compute_signal_score

# Source-type prefix mapping is used to gate "official" support. A record from
# FDA/EMA/MHRA/PMDA/SEC/USPTO/ClinicalTrials.gov counts as an official source.
_OFFICIAL_RANK_CEIL = 2


@dataclass
class VerificationResult:
    events: list[RegulatoryEvent] = field(default_factory=list)
    claims: list[VerifiedClaim] = field(default_factory=list)
    rejections: list[str] = field(default_factory=list)


class Verifier:
    """Merges candidates into normalized events, then issues VerifiedClaims.

    The verifier deliberately stays rule-based in Phase 2: it merges by the
    semantic event_key, classifies the support strength (official vs reported),
    and scores each resulting claim. A model-driven adjudicator can be slotted
    in later for ambiguous groupings without rewriting this layer.
    """

    def __init__(self, session: Session):
        self.session = session
        self._known_assets: dict[str, str] = {}

    def run(
        self,
        *,
        company_id: str,
        job_id: str | None,
        candidate_pairs: list[tuple[str, CandidateEvent]],
    ) -> VerificationResult:
        result = VerificationResult()

        # Pre-resolve the source ranks once so confidence classification can
        # treat regulator-rank documents as "official" support.
        doc_ranks = self._doc_official_ranks([sid for sid, _ in candidate_pairs])

        grouped = dedupe_events(candidate_pairs, asset_key_resolver=self._asset_key)
        for _, members in grouped.items():
            merged = self._merge_group(company_id, job_id, members)
            if merged is None:
                continue
            event, source_doc_ids = merged

            confidence, state = self._classify_support(source_doc_ids, doc_ranks)
            score = compute_signal_score(event)
            claim_text = self._claim_text(event)
            claim = VerifiedClaim(
                claim_id=f"clm_{uuid.uuid4().hex[:12]}",
                event_id=event.event_id,
                text=claim_text,
                verification_state=state,
                confidence=confidence,
                source_doc_ids=source_doc_ids,
                citation_numbers=[],  # assigned by the citation engine downstream
                signal_score=score,
            )

            self._persist_event(event)
            self._persist_claim(claim)
            result.events.append(event)
            result.claims.append(claim)

        return result

    # ----------------------------------------------------------------- assets
    def _asset_key(self, asset_name: str | None) -> str | None:
        if not asset_name:
            return None
        resolved = resolve_asset(asset_name, known_assets=self._known_assets)
        if resolved is None:
            return None
        canonical, key = resolved
        self._known_assets[key] = canonical
        return key

    def _ensure_asset(self, company_id: str, asset_name: str | None) -> str | None:
        if not asset_name:
            return None
        resolved = resolve_asset(asset_name, known_assets=self._known_assets)
        if resolved is None:
            return None
        canonical, key = resolved
        self._known_assets[key] = canonical

        existing = (
            self.session.query(AssetRow)
            .filter(AssetRow.company_id == company_id, AssetRow.name_key == key)
            .one_or_none()
        )
        if existing is not None:
            return existing.asset_id
        row = AssetRow(
            asset_id=f"ast_{uuid.uuid4().hex[:12]}",
            company_id=company_id,
            asset_name=canonical,
            name_key=key,
            aliases=[],
        )
        self.session.add(row)
        self.session.flush()
        return row.asset_id

    # --------------------------------------------------------------- merging
    def _merge_group(
        self,
        company_id: str,
        job_id: str | None,
        members: list[tuple[str, CandidateEvent]],
    ) -> tuple[RegulatoryEvent, list[str]] | None:
        if not members:
            return None
        members_sorted = sorted(members, key=lambda kv: kv[1].evidence_strength, reverse=True)
        head_doc_id, head = members_sorted[0]
        if head.event_date is None:
            return None

        source_doc_ids = list(dict.fromkeys(sid for sid, _ in members_sorted))
        asset_id = self._ensure_asset(company_id, head.asset_name)
        event = RegulatoryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            company_id=company_id,
            asset_id=asset_id,
            agency=head.agency,
            jurisdiction=head.jurisdiction,
            event_type=head.event_type,
            status=head.status,
            event_date=head.event_date,
            summary=head.summary,
            investor_importance=max(c.investor_importance for _, c in members_sorted),
            evidence_strength=max(c.evidence_strength for _, c in members_sorted),
            source_doc_ids=source_doc_ids,
        )
        return event, source_doc_ids

    # -------------------------------------------------------------- support
    def _doc_official_ranks(self, source_doc_ids: list[str]) -> dict[str, int]:
        if not source_doc_ids:
            return {}
        rows = (
            self.session.query(SourceDocumentRow.source_doc_id, SourceDocumentRow.official_rank)
            .filter(SourceDocumentRow.source_doc_id.in_(set(source_doc_ids)))
            .all()
        )
        return {sid: rank for sid, rank in rows}

    def _classify_support(
        self,
        source_doc_ids: list[str],
        doc_ranks: dict[str, int],
    ) -> tuple[Confidence, VerificationState]:
        official_count = sum(
            1 for sid in source_doc_ids if doc_ranks.get(sid, 5) <= _OFFICIAL_RANK_CEIL
        )
        total = len(source_doc_ids)
        if official_count >= 1 and total >= 2:
            return Confidence.HIGH, VerificationState.VERIFIED
        if official_count >= 1:
            return Confidence.HIGH, VerificationState.VERIFIED
        if total >= 2:
            return Confidence.MEDIUM, VerificationState.PARTIALLY_VERIFIED
        return Confidence.LOW, VerificationState.REPORTED_ONLY

    # -------------------------------------------------------------- claim text
    @staticmethod
    def _claim_text(event: RegulatoryEvent) -> str:
        date_str = event.event_date.isoformat()
        asset_tag = f" ({event.summary})" if event.summary else ""
        return (
            f"{event.agency} {event.event_type.replace('_', ' ')} "
            f"on {date_str} — {event.status}.{asset_tag}"
        )

    # ----------------------------------------------------------- persistence
    def _persist_event(self, event: RegulatoryEvent) -> None:
        key = event_key(
            agency=event.agency,
            jurisdiction=event.jurisdiction,
            event_type=event.event_type,
            event_date=event.event_date,
            asset_key=event.asset_id,
        )
        existing = (
            self.session.query(RegulatoryEventRow)
            .filter(
                RegulatoryEventRow.company_id == event.company_id,
                RegulatoryEventRow.event_key == key,
            )
            .one_or_none()
        )
        if existing is not None:
            # Replace event_id so downstream claim references resolve.
            event.event_id = existing.event_id
            existing.source_doc_ids = sorted(
                set(existing.source_doc_ids or []) | set(event.source_doc_ids)
            )
            existing.investor_importance = max(
                existing.investor_importance, event.investor_importance
            )
            existing.evidence_strength = max(existing.evidence_strength, event.evidence_strength)
            self.session.add(existing)
            self.session.flush()
            return
        self.session.add(
            RegulatoryEventRow(
                event_id=event.event_id,
                company_id=event.company_id,
                asset_id=event.asset_id,
                agency=event.agency,
                jurisdiction=event.jurisdiction,
                event_type=event.event_type,
                status=event.status,
                event_date=event.event_date,
                summary=event.summary,
                investor_importance=event.investor_importance,
                evidence_strength=event.evidence_strength,
                source_doc_ids=event.source_doc_ids,
                event_key=key,
            )
        )
        self.session.flush()

    def _persist_claim(self, claim: VerifiedClaim) -> None:
        self.session.add(
            ClaimRow(
                claim_id=claim.claim_id,
                event_id=claim.event_id,
                text=claim.text,
                verification_state=claim.verification_state.value,
                confidence=claim.confidence.value,
                source_doc_ids=claim.source_doc_ids,
                citation_numbers=claim.citation_numbers,
                signal_score=claim.signal_score,
            )
        )
        self.session.flush()
