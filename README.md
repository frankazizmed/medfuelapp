# MedFuel — Regulatory Intelligence Pipeline (Phase 1)

Phase 1 of the MedFuel regulatory analysis engine: regulator-first connectors and
a provenance-first document registry. No extraction, scoring, or narrative yet —
those are Phase 2 and Phase 3 per the design.

## Scope

- **Canonical entity model** for companies under diligence (`CompanyIdentity`, CIK normalization, alias/domain merge on upsert).
- **Official-source adapters**: FDA (openFDA), SEC (data.sec.gov), ClinicalTrials.gov v2, NCBI E-utilities (PubMed), EMA medicines JSON, USPTO Open Data Portal.
- **Page-centric adapters via Firecrawl**: MHRA Products + PARs, PMDA English review reports, company websites / IR pages.
- **Document registry** with content-hash dedupe, immutable inserts, and an `audit_events` stream for every insert / duplicate-skip / status change.
- **Rate-limit-aware HTTP client** with per-host limiters, polite `User-Agent` / `From` headers, and exponential-backoff retries on 429/5xx.
- **FastAPI surface** — `POST /v1/regulatory/jobs`, `GET /v1/regulatory/jobs/{job_id}`, `GET /health` — backed by FastAPI `BackgroundTasks`.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # then edit MEDFUEL_CONTACT_EMAIL / MEDFUEL_USER_AGENT
pytest
uvicorn medfuel.main:app --reload
```

Default datastore is SQLite (`./medfuel.sqlite`); set `MEDFUEL_DATABASE_URL`
to a Postgres or Supabase URL to switch.

## Source-rank ordering (drives downstream signal scoring)

| Rank | Sources |
| ---- | ------- |
| 1    | FDA, EMA, MHRA, PMDA |
| 2    | ClinicalTrials.gov, SEC, USPTO, PubMed |
| 4    | Company websites |
| 5    | Investor decks |

Regulator records outrank company claims when the two conflict — extraction and
verification in Phase 2 will rely on this ordering.

## Layout

```
src/medfuel/
  config.py           env-driven settings (rate limits, API keys, DB URL)
  models/schemas.py   Pydantic types (CompanyIdentity, RawSourceRecord, ...)
  db/                 SQLAlchemy ORM, session, document registry, audit stream
  http/client.py      RateLimitedClient + per-host RateLimiter
  adapters/           one adapter per source; SourceAdapter ABC at base.py
  ingest/pipeline.py  fan-out discovery + persistence
  api/routes.py       FastAPI routes
  main.py             create_app()
tests/                pytest + respx + sqlite in-memory
```

## Operator notes

- SEC + NCBI both expect a contact email in the `User-Agent` / `From` header;
  `MEDFUEL_CONTACT_EMAIL` is wired into both.
- Without `MEDFUEL_FIRECRAWL_API_KEY`, MHRA/PMDA/company-web adapters degrade
  to no-ops (pipeline still runs) so local dev does not require third-party keys.
- Adapter failures never abort the pipeline — they are captured per-adapter as
  error strings in `DiscoveryResult.errors` and recorded on the `JobRow`.
- Every insert / duplicate-skip / status transition emits an `audit_events`
  row keyed by `entity_type` + `entity_id`.

## Not in scope (Phase 2+)

- Structured extraction (OpenAI Responses + Structured Outputs)
- Verification, claim/citation graph, signal scoring
- Narrative generation (Claude Opus 4.7 default)
- pgvector chunk store, embeddings, ANN/exact search
- Report rendering and adaptive pagination
