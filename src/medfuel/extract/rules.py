from __future__ import annotations

from medfuel.extract.base import Extractor
from medfuel.extract.normalize import normalize_date
from medfuel.models import CandidateEvent, RawSourceRecord, SourceType


class RuleBasedExtractor(Extractor):
    """Deterministic extractor for structured source payloads.

    Each source-type branch maps adapter payload shape to one or more
    CandidateEvent records. Unstructured sources (MHRA/PMDA search results,
    company sites) return nothing here and are intended for the LLM extractor.
    """

    name = "rule"

    async def extract(
        self,
        *,
        source_doc_id: str,
        record: RawSourceRecord,
    ) -> list[CandidateEvent]:
        match record.source_type:
            case SourceType.FDA:
                return self._from_fda(source_doc_id, record)
            case SourceType.SEC:
                return self._from_sec(source_doc_id, record)
            case SourceType.CLINICALTRIALS:
                return self._from_ctgov(source_doc_id, record)
            case SourceType.PUBMED:
                return self._from_pubmed(source_doc_id, record)
            case SourceType.EMA:
                return self._from_ema(source_doc_id, record)
            case SourceType.USPTO:
                return self._from_uspto(source_doc_id, record)
            case _:
                return []

    # ---------------------------------------------------------------- FDA
    def _from_fda(self, source_doc_id: str, rec: RawSourceRecord) -> list[CandidateEvent]:
        payload = rec.payload or {}
        url = str(rec.url)
        if "device/510k.json" in url:
            return self._fda_510k(source_doc_id, rec, payload)
        if "drug/drugsfda.json" in url:
            return self._fda_drugsfda(source_doc_id, rec, payload)
        if "drug/label.json" in url:
            return self._fda_label(source_doc_id, rec, payload)
        return []

    def _fda_510k(
        self, source_doc_id: str, rec: RawSourceRecord, p: dict
    ) -> list[CandidateEvent]:
        event_date = normalize_date(p.get("decision_date") or p.get("date_received"))
        if event_date is None:
            return []
        asset = p.get("device_name") or p.get("trade_name") or p.get("k_number")
        decision = (p.get("decision_description") or p.get("decision_code") or "").strip()
        return [
            CandidateEvent(
                agency="FDA",
                jurisdiction="US",
                event_type="clearance",
                status=decision or "510(k) decision",
                event_date=event_date,
                summary=f"FDA 510(k) {p.get('k_number')}: {decision or 'cleared'} ({asset}).",
                asset_name=asset,
                investor_importance=4,
                evidence_strength=5,
                source_doc_id=source_doc_id,
                source_excerpt=p.get("k_number"),
            )
        ]

    def _fda_drugsfda(
        self, source_doc_id: str, rec: RawSourceRecord, p: dict
    ) -> list[CandidateEvent]:
        out: list[CandidateEvent] = []
        app_number = p.get("application_number")
        brand = None
        if p.get("openfda"):
            brand = (p["openfda"].get("brand_name") or [None])[0]
        for sub in p.get("submissions") or []:
            sub_status = sub.get("submission_status")
            sub_date = normalize_date(sub.get("submission_status_date"))
            if sub_date is None:
                continue
            is_approval = sub_status and sub_status.upper() == "AP"
            event_type = "approval" if is_approval else "label_change"
            out.append(
                CandidateEvent(
                    agency="FDA",
                    jurisdiction="US",
                    event_type=event_type,
                    status=sub_status or "submission",
                    event_date=sub_date,
                    summary=(
                        f"FDA {event_type.replace('_', ' ')} for {brand or app_number} "
                        f"({sub.get('submission_class_code') or sub.get('submission_type', '')})."
                    ),
                    asset_name=brand or app_number,
                    investor_importance=5 if is_approval else 3,
                    evidence_strength=5,
                    source_doc_id=source_doc_id,
                    source_excerpt=app_number,
                )
            )
        if not out and app_number:
            # No submission timeline; still surface the application itself as a marker.
            event_date = normalize_date(rec.published_at)
            if event_date is not None:
                out.append(
                    CandidateEvent(
                        agency="FDA",
                        jurisdiction="US",
                        event_type="offering_or_filing",
                        status="application",
                        event_date=event_date,
                        summary=f"FDA application {app_number} associated with {brand or app_number}.",
                        asset_name=brand or app_number,
                        investor_importance=3,
                        evidence_strength=4,
                        source_doc_id=source_doc_id,
                    )
                )
        return out

    def _fda_label(
        self, source_doc_id: str, rec: RawSourceRecord, p: dict
    ) -> list[CandidateEvent]:
        event_date = normalize_date(p.get("effective_time") or rec.published_at)
        if event_date is None:
            return []
        brand = None
        if p.get("openfda"):
            brand = (p["openfda"].get("brand_name") or [None])[0]
        return [
            CandidateEvent(
                agency="FDA",
                jurisdiction="US",
                event_type="label_change",
                status="label update",
                event_date=event_date,
                summary=f"FDA label update effective {event_date.isoformat()} for {brand or 'product'}.",
                asset_name=brand,
                investor_importance=3,
                evidence_strength=4,
                source_doc_id=source_doc_id,
            )
        ]

    # ---------------------------------------------------------------- SEC
    def _from_sec(self, source_doc_id: str, rec: RawSourceRecord) -> list[CandidateEvent]:
        p = rec.payload or {}
        form = (p.get("form") or "").upper()
        filing_date = normalize_date(p.get("filingDate") or rec.published_at)
        if filing_date is None or not form:
            return []
        # Importance heuristic: 8-K material events and S-1 IPO filings rank highest.
        importance = 4 if form in {"8-K", "S-1", "10-K"} else 3
        return [
            CandidateEvent(
                agency="SEC",
                jurisdiction="US",
                event_type="offering_or_filing",
                status=form,
                event_date=filing_date,
                summary=f"SEC {form} filed on {filing_date.isoformat()} (accession {p.get('accession')}).",
                investor_importance=importance,
                evidence_strength=5,
                source_doc_id=source_doc_id,
                source_excerpt=p.get("accession"),
            )
        ]

    # ----------------------------------------------------- ClinicalTrials.gov
    def _from_ctgov(self, source_doc_id: str, rec: RawSourceRecord) -> list[CandidateEvent]:
        p = rec.payload or {}
        protocol = p.get("protocolSection") or {}
        ident = protocol.get("identificationModule") or {}
        status = protocol.get("statusModule") or {}
        last_update = (status.get("lastUpdatePostDateStruct") or {}).get("date")
        event_date = normalize_date(last_update or rec.published_at)
        if event_date is None:
            return []
        overall_status = status.get("overallStatus") or "Unknown"
        is_terminated = overall_status.lower() in {"terminated", "withdrawn", "suspended"}
        event_type = "clinical_hold" if is_terminated else "trial_update"
        title = ident.get("briefTitle") or ident.get("officialTitle") or ident.get("nctId")
        return [
            CandidateEvent(
                agency="ClinicalTrials.gov",
                jurisdiction="GLOBAL",
                event_type=event_type,
                status=overall_status,
                event_date=event_date,
                summary=f"Trial {ident.get('nctId')}: {overall_status} ({title}).",
                asset_name=title,
                investor_importance=4 if is_terminated else 3,
                evidence_strength=4,
                source_doc_id=source_doc_id,
                source_excerpt=ident.get("nctId"),
            )
        ]

    # ---------------------------------------------------------------- PubMed
    def _from_pubmed(self, source_doc_id: str, rec: RawSourceRecord) -> list[CandidateEvent]:
        # PubMed records are evidence rather than regulatory events; they are
        # used for citation support, not first-class events. Returning [] here
        # keeps PubMed as supporting context only.
        return []

    # ---------------------------------------------------------------- EMA
    def _from_ema(self, source_doc_id: str, rec: RawSourceRecord) -> list[CandidateEvent]:
        p = rec.payload or {}
        event_date = normalize_date(p.get("authorisation_date") or rec.published_at)
        if event_date is None:
            return []
        return [
            CandidateEvent(
                agency="EMA",
                jurisdiction="EU",
                event_type="approval",
                status=p.get("authorisation_status", "authorised"),
                event_date=event_date,
                summary=f"EMA authorisation for {p.get('name') or p.get('active_substance')}.",
                asset_name=p.get("name") or p.get("active_substance"),
                investor_importance=5,
                evidence_strength=5,
                source_doc_id=source_doc_id,
                source_excerpt=p.get("ema_number") or p.get("eu_number"),
            )
        ]

    # ---------------------------------------------------------------- USPTO
    def _from_uspto(self, source_doc_id: str, rec: RawSourceRecord) -> list[CandidateEvent]:
        p = rec.payload or {}
        event_date = normalize_date(p.get("patentDate") or p.get("filingDate") or rec.published_at)
        if event_date is None:
            return []
        return [
            CandidateEvent(
                agency="USPTO",
                jurisdiction="US",
                event_type="patent_event",
                status="granted" if p.get("patentDate") else "filed",
                event_date=event_date,
                summary=(
                    f"USPTO patent {p.get('patentNumber') or p.get('applicationNumber')}: "
                    f"{p.get('inventionTitle') or p.get('title') or 'untitled'}."
                ),
                asset_name=p.get("inventionTitle"),
                investor_importance=2,
                evidence_strength=4,
                source_doc_id=source_doc_id,
            )
        ]
