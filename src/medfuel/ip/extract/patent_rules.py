"""Rule-based IP extractor.

Converts a RawSourceRecord from any IP source adapter into a typed
PatentRecord (or returns None when the payload doesn't represent a
patent — e.g. PTAB proceedings, assignment events, litigation
dockets, all of which take a different downstream path).
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from medfuel.extract.normalize import normalize_date
from medfuel.ip.extract.claim_parser import parse_claims
from medfuel.ip.models import (
    AssignmentEvent,
    FilingKind,
    IPSourceType,
    LegalStatus,
    LitigationRecord,
    PatentRecord,
    PTABProceeding,
)
from medfuel.models.schemas import RawSourceRecord, SourceType


class RuleBasedIPExtractor:
    """Deterministic IP extractor over structured adapter payloads."""

    name = "ip_rule"

    def extract_patent(
        self,
        *,
        source_doc_id: str,
        record: RawSourceRecord,
    ) -> PatentRecord | None:
        match record.source_type:
            case SourceType.PATENTSVIEW:
                return self._from_patentsview(source_doc_id, record)
            case SourceType.USPTO:
                return self._from_uspto(source_doc_id, record)
            case SourceType.EPO:
                return self._from_epo(source_doc_id, record)
            case SourceType.GOOGLE_PATENTS:
                return self._from_google(source_doc_id, record)
            case _:
                return None

    def extract_proceeding(
        self,
        *,
        source_doc_id: str,
        record: RawSourceRecord,
    ) -> PTABProceeding | None:
        if record.source_type != SourceType.PTAB:
            return None
        p = record.payload or {}
        proc_id = str(p.get("proceedingNumber") or p.get("id") or source_doc_id)
        patent_number = str(
            p.get("respondentPatentNumber") or p.get("patentNumber") or ""
        )
        kind_raw = str(p.get("proceedingTypeCategory") or p.get("type") or "").upper()
        kind = "IPR" if "IPR" in kind_raw else "PGR" if "PGR" in kind_raw else "CBM" if "CBM" in kind_raw else "OTHER"
        return PTABProceeding(
            proceeding_id=proc_id,
            patent_number=patent_number,
            type=kind,  # type: ignore[arg-type]
            petitioner=p.get("petitionerPartyName"),
            filing_date=normalize_date(p.get("filingDate")),
            status=p.get("currentStatus") or p.get("status"),
            outcome=p.get("decisionDate") and "decided" or None,
            source_doc_id=source_doc_id,
        )

    def extract_litigation(
        self,
        *,
        source_doc_id: str,
        record: RawSourceRecord,
    ) -> LitigationRecord | None:
        if record.source_type != SourceType.LITIGATION:
            return None
        p = record.payload or {}
        docket = str(p.get("docketNumber") or p.get("docket_number") or source_doc_id)
        return LitigationRecord(
            docket_id=docket,
            court=p.get("court") or p.get("court_id"),
            plaintiffs=[s for s in [p.get("plaintiff")] if s],
            defendants=[s for s in [p.get("defendant")] if s],
            patent_numbers=_patent_numbers_from_text(
                f"{p.get('caseName') or ''} {p.get('description') or ''}"
            ),
            filing_date=normalize_date(p.get("dateFiled") or p.get("date_filed")),
            status=p.get("status"),
            source_doc_id=source_doc_id,
        )

    def extract_assignment(
        self,
        *,
        source_doc_id: str,
        record: RawSourceRecord,
    ) -> AssignmentEvent | None:
        if record.source_type != SourceType.USPTO_ASSIGNMENT:
            return None
        p = record.payload or {}
        assignment_id = str(p.get("reelFrame") or p.get("id") or source_doc_id)
        return AssignmentEvent(
            assignment_id=assignment_id,
            patent_or_application=str(p.get("patentNumber") or p.get("applicationNumber") or ""),
            assignor=p.get("assignorName") or p.get("assignor"),
            assignee=p.get("assigneeName") or p.get("assignee"),
            recorded_date=normalize_date(p.get("recordedDate") or p.get("recorded_date")),
            nature=p.get("conveyanceText") or p.get("nature"),
            source_doc_id=source_doc_id,
        )

    # --------------------------------------------------------------- patent variants

    def _from_patentsview(self, source_doc_id: str, rec: RawSourceRecord) -> PatentRecord | None:
        p = rec.payload or {}
        pub = str(p.get("patent_number") or p.get("patent_id") or "")
        if not pub:
            return None
        filing = (
            normalize_date((p.get("application") or [{}])[0].get("filing_date"))
            if isinstance(p.get("application"), list)
            else normalize_date(p.get("application_filing_date"))
        )
        grant = normalize_date(p.get("patent_date"))
        priority = normalize_date(p.get("earliest_priority_date")) or filing
        kind = _kind_from_text(p.get("patent_kind") or "")
        assignees = _string_list(p.get("assignees"), "assignee_organization")
        inventors = [
            f"{i.get('inventor_name_first', '')} {i.get('inventor_name_last', '')}".strip()
            for i in (p.get("inventors") or [])
        ]
        cpc = _string_list(p.get("cpc_current"), "cpc_subclass_id")
        claims = parse_claims(p.get("claims"))
        ind_count = sum(1 for c in claims if c.is_independent)
        dep_count = sum(1 for c in claims if not c.is_independent)
        expiration = _expiration_estimate(grant=grant, priority=priority, kind=kind)
        return PatentRecord(
            patent_id=f"ip_{pub}",
            publication_number=pub,
            application_number=(p.get("application") or [{}])[0].get("application_number")
            if isinstance(p.get("application"), list)
            else None,
            title=p.get("patent_title") or pub,
            jurisdiction="US",
            kind=kind,
            filing_date=filing,
            priority_date=priority,
            publication_date=grant,
            grant_date=grant,
            expiration_estimate=expiration,
            legal_status=LegalStatus.GRANTED if grant else LegalStatus.PENDING,
            assignees=assignees,
            inventors=[i for i in inventors if i],
            cpc_codes=cpc,
            forward_citations=int(p.get("patent_num_cited_by_us_patents") or 0),
            backward_citations=int(p.get("patent_num_us_patent_citations") or 0),
            independent_claim_count=ind_count,
            dependent_claim_count=dep_count,
            claims=claims,
            source_doc_ids=[source_doc_id],
            primary_source=IPSourceType.PATENTSVIEW,
        )

    def _from_uspto(self, source_doc_id: str, rec: RawSourceRecord) -> PatentRecord | None:
        p = rec.payload or {}
        pub = str(p.get("patentNumber") or p.get("applicationNumber") or "")
        if not pub:
            return None
        filing = normalize_date(p.get("filingDate"))
        grant = normalize_date(p.get("patentDate"))
        priority = filing
        expiration = _expiration_estimate(grant=grant, priority=priority, kind=FilingKind.UTILITY)
        assignees = [a for a in [p.get("patentAssignee"), p.get("assigneeName")] if a]
        return PatentRecord(
            patent_id=f"ip_{pub}",
            publication_number=str(p.get("patentNumber")) if p.get("patentNumber") else None,
            application_number=str(p.get("applicationNumber")) if p.get("applicationNumber") else None,
            title=p.get("inventionTitle") or p.get("title") or pub,
            jurisdiction="US",
            kind=FilingKind.UTILITY,
            filing_date=filing,
            priority_date=priority,
            grant_date=grant,
            expiration_estimate=expiration,
            legal_status=LegalStatus.GRANTED if grant else LegalStatus.PENDING,
            assignees=assignees,
            source_doc_ids=[source_doc_id],
            primary_source=IPSourceType.USPTO,
        )

    def _from_epo(self, source_doc_id: str, rec: RawSourceRecord) -> PatentRecord | None:
        p = rec.payload or {}
        doc_id = p.get("document-id") or {}
        country = doc_id.get("country", {}).get("$") or "EP"
        number = doc_id.get("doc-number", {}).get("$")
        kind = doc_id.get("kind", {}).get("$") or ""
        if not number:
            return None
        pub = f"{country}{number}{kind}".strip()
        return PatentRecord(
            patent_id=f"ip_{pub}",
            publication_number=pub,
            title=f"EPO {pub}",
            jurisdiction=country,
            kind=FilingKind.UTILITY,
            legal_status=LegalStatus.UNKNOWN,
            source_doc_ids=[source_doc_id],
            primary_source=IPSourceType.EPO,
        )

    def _from_google(self, source_doc_id: str, rec: RawSourceRecord) -> PatentRecord | None:
        p = rec.payload or {}
        url = str(rec.url)
        pub = _patent_id_from_google_url(url) or rec.title
        if not pub:
            return None
        return PatentRecord(
            patent_id=f"ip_{pub}",
            publication_number=pub,
            title=p.get("title") or rec.title,
            jurisdiction=_jurisdiction_from_pub(pub),
            kind=FilingKind.UTILITY,
            legal_status=LegalStatus.UNKNOWN,
            source_doc_ids=[source_doc_id],
            primary_source=IPSourceType.GOOGLE_PATENTS,
        )


# --------------------------------------------------------------------------- helpers

_PATENT_NUM_RE = re.compile(r"\b(US|EP|WO|JP|CN|KR|CA)?\s*-?\s*([0-9]{6,10})(?:[A-Z]\d?)?\b")


def _patent_numbers_from_text(text: str) -> list[str]:
    return ["".join(parts).replace(" ", "") for parts in _PATENT_NUM_RE.findall(text or "")]


def _string_list(items: list[dict] | None, key: str) -> list[str]:
    if not items:
        return []
    out: list[str] = []
    for item in items:
        value = item.get(key)
        if value:
            out.append(value)
    return out


def _kind_from_text(raw: str) -> FilingKind:
    r = raw.lower()
    if "design" in r:
        return FilingKind.DESIGN
    if "provisional" in r:
        return FilingKind.PROVISIONAL
    if "reissue" in r:
        return FilingKind.REISSUE
    if "pct" in r:
        return FilingKind.PCT
    if "continuation in part" in r or "cip" in r:
        return FilingKind.CONTINUATION_IN_PART
    if "continuation" in r:
        return FilingKind.CONTINUATION
    if "divisional" in r:
        return FilingKind.DIVISIONAL
    return FilingKind.UTILITY


def _expiration_estimate(*, grant: date | None, priority: date | None, kind: FilingKind) -> date | None:
    """Estimate expiration as priority date + 20 years for utility patents.

    This is a deliberate simplification (no PTA, no terminal disclaimers,
    no FDA-linked term extensions). Surface as INFERRED in the verifier
    when material to a finding.
    """
    if kind == FilingKind.DESIGN and grant:
        return grant.replace(year=grant.year + 15)
    base = priority or grant
    if base is None:
        return None
    try:
        return base.replace(year=base.year + 20)
    except ValueError:
        # Leap-day fall through.
        return base + timedelta(days=365 * 20)


_PUB_PREFIX_RE = re.compile(r"^([A-Z]{2})")


def _jurisdiction_from_pub(pub: str) -> str:
    m = _PUB_PREFIX_RE.match(pub)
    return m.group(1) if m else "US"


def _patent_id_from_google_url(url: str) -> str | None:
    parts = url.rstrip("/").split("/")
    if "patent" not in parts:
        return None
    idx = parts.index("patent")
    return parts[idx + 1] if idx + 1 < len(parts) else None
