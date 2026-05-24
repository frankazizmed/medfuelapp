from __future__ import annotations

import re
from datetime import date, datetime

from dateutil import parser as dateparser

# Canonical agency names. Keeps regulatory_events.agency consistent across
# adapters even when source payloads use different casings or abbreviations.
_AGENCY_CANONICAL: dict[str, str] = {
    "fda": "FDA",
    "u.s. food and drug administration": "FDA",
    "food and drug administration": "FDA",
    "ema": "EMA",
    "european medicines agency": "EMA",
    "mhra": "MHRA",
    "medicines and healthcare products regulatory agency": "MHRA",
    "pmda": "PMDA",
    "pharmaceuticals and medical devices agency": "PMDA",
    "sec": "SEC",
    "u.s. securities and exchange commission": "SEC",
    "uspto": "USPTO",
    "united states patent and trademark office": "USPTO",
    "clinicaltrials.gov": "ClinicalTrials.gov",
    "nih": "NIH",
}


def normalize_agency(raw: str | None) -> str:
    if not raw:
        return "Unknown"
    key = raw.strip().lower()
    return _AGENCY_CANONICAL.get(key, raw.strip())


def normalize_date(value: str | datetime | date | None) -> date | None:
    """Parse heterogeneous date strings (YYYYMMDD, YYYY-MM-DD, RFC 3339...) into a date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    # Compact YYYYMMDD form used by openFDA.
    compact = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", text)
    if compact:
        y, m, d = map(int, compact.groups())
        try:
            return date(y, m, d)
        except ValueError:
            return None
    try:
        return dateparser.parse(text).date()
    except (ValueError, TypeError, OverflowError):
        return None


_NAME_NOISE = re.compile(r"[®™©]|\(.*?\)|\s+")


def _name_key(name: str) -> str:
    return _NAME_NOISE.sub(" ", name).strip().lower()


def resolve_asset(
    asset_name: str | None,
    *,
    known_assets: dict[str, str],
) -> tuple[str, str] | None:
    """Return (canonical_name, name_key) for an asset string.

    `known_assets` maps name_key -> canonical asset name. The first time an
    asset is seen the caller mints a new asset row; subsequent sightings
    resolve to the same key, which is how aliases collapse onto one asset_id.
    """
    if not asset_name:
        return None
    key = _name_key(asset_name)
    if not key:
        return None
    canonical = known_assets.get(key, asset_name.strip())
    return canonical, key
