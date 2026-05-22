from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class SourceType(str, Enum):
    FDA = "fda"
    EMA = "ema"
    MHRA = "mhra"
    PMDA = "pmda"
    CLINICALTRIALS = "clinicaltrials"
    SEC = "sec"
    USPTO = "uspto"
    PUBMED = "pubmed"
    COMPANY = "company"
    INVESTOR_DECK = "investor_deck"
    # IP intelligence sources. Keep ordered with regulatory sources so
    # OFFICIAL_RANK below is the single source of truth for citation weight.
    PATENTSVIEW = "patentsview"
    GOOGLE_PATENTS = "google_patents"
    EPO = "epo"
    WIPO = "wipo"
    USPTO_ASSIGNMENT = "uspto_assignment"
    PTAB = "ptab"
    LITIGATION = "litigation"
    SEC_IP = "sec_ip"
    COMPANY_IP = "company_ip"


# Source ranking (1 = highest authority, 5 = lowest). Drives later signal scoring.
OFFICIAL_RANK: dict[SourceType, int] = {
    SourceType.FDA: 1,
    SourceType.EMA: 1,
    SourceType.MHRA: 1,
    SourceType.PMDA: 1,
    SourceType.CLINICALTRIALS: 2,
    SourceType.SEC: 2,
    SourceType.USPTO: 2,
    SourceType.PUBMED: 2,
    SourceType.COMPANY: 4,
    SourceType.INVESTOR_DECK: 5,
    # IP sources: patent offices and tribunals at rank 1; aggregators at 2-3.
    SourceType.EPO: 1,
    SourceType.WIPO: 1,
    SourceType.USPTO_ASSIGNMENT: 1,
    SourceType.PTAB: 1,
    SourceType.LITIGATION: 1,
    SourceType.PATENTSVIEW: 2,
    SourceType.SEC_IP: 2,
    SourceType.GOOGLE_PATENTS: 3,
    SourceType.COMPANY_IP: 4,
}


class CompanyIdentity(BaseModel):
    """Caller-supplied identity for a company under diligence."""

    name: str
    aliases: list[str] = Field(default_factory=list)
    ticker: str | None = None
    cik: str | None = None
    domains: list[str] = Field(default_factory=list)

    def canonical_cik(self) -> str | None:
        # SEC submissions endpoints expect zero-padded 10-digit CIK strings.
        if not self.cik:
            return None
        digits = "".join(c for c in self.cik if c.isdigit())
        return digits.zfill(10) if digits else None


class JurisdictionScope(BaseModel):
    jurisdictions: list[str] = Field(default_factory=lambda: ["US", "EU", "UK", "JP"])
    lookback_years: int = 10
    sources: list[SourceType] = Field(default_factory=lambda: list(SourceType))


class RawSourceRecord(BaseModel):
    """A single document or API payload returned by an adapter.

    Persistence is provenance-first: URL, content_hash, source_type, jurisdiction,
    and official_rank are required for downstream verification.
    """

    model_config = ConfigDict(use_enum_values=False)

    source_type: SourceType
    jurisdiction: str
    url: HttpUrl
    title: str
    payload: dict[str, Any] = Field(default_factory=dict)
    published_at: datetime | None = None
    retrieved_at: datetime
    page_locator: str | None = None
    external_id: str | None = None
    content_hash: str
    official_rank: int = Field(ge=1, le=5)


class DiscoveryResult(BaseModel):
    """Summary returned by the discovery pipeline."""

    company_id: str
    job_id: str
    records_collected: int
    records_persisted_new: int
    records_persisted_duplicate: int
    by_source: dict[SourceType, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    events_persisted: int = 0
    claims_persisted: int = 0
    report_id: str | None = None
