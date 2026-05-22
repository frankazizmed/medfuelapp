"""openFDA drug + approval source fetcher.

Docs: https://open.fda.gov/apis/drug/drugsfda/
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from clinical_evidence.discovery._http import fetch_json, sha256
from clinical_evidence.schemas import CompanyContext, DiscoveryResult, RawDocument, SourceKind

log = logging.getLogger(__name__)

_DRUGS_FDA = "https://api.fda.gov/drug/drugsfda.json"
_LABEL = "https://api.fda.gov/drug/label.json"


async def fetch(company: CompanyContext) -> DiscoveryResult:
    """Pull drug records + labels for the sponsor and each asset."""

    docs: list[RawDocument] = []
    now = datetime.now(timezone.utc)
    queries: list[tuple[str, str]] = []
    sponsor_query = f'sponsor_name:"{company.name}"'
    queries.append(("drugsfda", sponsor_query))
    for asset in company.assets:
        queries.append(("label", f'openfda.brand_name:"{asset}" openfda.generic_name:"{asset}"'))

    for kind, q in queries:
        url = _DRUGS_FDA if kind == "drugsfda" else _LABEL
        try:
            data = await fetch_json(url, params={"search": q, "limit": 20})
        except Exception as exc:  # noqa: BLE001
            log.warning("openFDA fetch failed (%s): %s", q, exc)
            continue
        for rec in (data or {}).get("results", []):
            text = json.dumps(rec, indent=2)
            ident = rec.get("application_number") or rec.get("set_id") or sha256(text)[:12]
            doc = RawDocument(
                doc_id=f"fda-{kind}-{ident}",
                company_id=company.company_id,
                source=SourceKind.fda,
                url=f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={ident}"
                if kind == "drugsfda"
                else f"https://labels.fda.gov/getInfo?setid={ident}",
                title=f"openFDA {kind}: {ident}",
                fetched_at=now,
                text=text,
                metadata={"openfda_kind": kind, "query": q},
                sha256=sha256(text),
            )
            docs.append(doc)

    log.info("openFDA returned %d records for %s", len(docs), company.name)
    return DiscoveryResult(documents=docs)
