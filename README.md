# MedFuel — Regulatory + IP Intelligence Pipeline

End-to-end life-sciences diligence engine. Two parallel modules share
one registry, citations engine, and narrator:

- **Regulatory** (phases 1-3): FDA / EMA / MHRA / PMDA / SEC /
  ClinicalTrials / USPTO / PubMed connectors, rule + LLM extraction,
  verification, 6-page institutional report.
- **IP Intelligence** (phase 4): USPTO / PatentsView / Google Patents
  / EPO / USPTO Assignments / PTAB / litigation connectors, claim
  parsing, family construction, six-framework scoring + signal/noise
  filter, 5-page institutional IP diligence narrative.

## What the system does

```
Company request
  → official-source adapters + Firecrawl web ingest
  → document registry (immutable, content-hash dedupe, audit stream)
  → rule-based extraction over structured payloads
  → normalize (dates, agencies, asset aliases)
  → dedupe by semantic event key
  → verify (rule-based support classification, confidence)
  → score (relevance/evidence/uniqueness/investor weights → 0–100 signal)
  → layout (six-page baseline; mechanical expansion up to ten pages)
  → citations (per-claim inline numbering, persisted per report run)
  → narrative (Claude Opus 4.7 in production; templated stub in CI)
  → persisted report run + REST endpoints for retrieval and rerender
```

## Source layer (Phase 1)

- **Official-source adapters**: FDA (openFDA), SEC (data.sec.gov),
  ClinicalTrials.gov v2, NCBI E-utilities (PubMed), EMA medicines JSON,
  USPTO Open Data Portal.
- **Page-centric adapters via Firecrawl**: MHRA Products + PARs, PMDA
  English review reports, company websites. No-op gracefully without a
  Firecrawl key so the rest of the pipeline keeps working offline.
- **Document registry** with `content_hash` dedupe, immutable inserts,
  and an `audit_events` stream over every insert / duplicate-skip /
  status transition.
- **Rate-limit-aware async HTTP client** with per-host limiters, polite
  `User-Agent` / `From` headers, and exponential-backoff retries on 429/5xx.

## Extraction and verification (Phase 2)

- **Rule-based extractor** for structured payloads (FDA 510(k),
  Drugs@FDA, drug labels, SEC submissions, CT.gov studies, EMA medicines,
  USPTO patents). Returns typed `CandidateEvent` records.
- **LLM extractor abstraction** wired to OpenAI Structured Outputs
  (lazy import, optional dep). Defaults to a deterministic stub when
  `MEDFUEL_USE_LLM=0`, keeping CI hermetic.
- **Normalization**: date parsing (compact YYYYMMDD, ISO, free text),
  agency canonicalization, asset alias resolution with cached canonical
  names.
- **Semantic dedupe** on `(agency, jurisdiction, event_type, date, asset)`.
- **Verifier** classifies each merged event as `high / medium / low`
  confidence and `verified / partially_verified / reported_only` state
  using the official-rank ordering of its supporting documents.
- **Per-event audit**: every extractor output is persisted in an
  `extractions` table for replay.

## Scoring, layout, narrative, reports (Phase 3)

- **Signal score** = `100 × (0.30·relevance + 0.30·evidence + 0.15·uniqueness + 0.25·investor)` per the design doc.
- **Six-page baseline** with explicit per-section word budgets:
  - Executive summary (260–320 words)
  - Pathway matrix (180–240)
  - Timeline (160–220)
  - Trials and evidence (280–360)
  - Safety, quality, compliance (260–340)
  - Implications and watchlist (220–300)
- **Mechanical pagination engine** expands the baseline by +1 page per
  trigger (omitted critical items, omitted high-signal share > 10%),
  capped at ten pages.
- **Citation engine** assigns stable inline numbers per claim and
  persists `citations` rows keyed to the report run.
- **Narrative renderer** drives the configured `NarratorLLM` (Claude
  Opus 4.7 in production; templated stub in CI) with the fixed report
  skeleton and citation tags.
- **Persisted report runs** + REST endpoints for retrieval, narrative
  download, citations, and rerender at a new page budget.

## API surface

```http
POST /v1/regulatory/jobs                      # 202 + job_id, runs in background
GET  /v1/regulatory/jobs/{job_id}             # status + result summary
GET  /v1/regulatory/reports/{report_id}       # layout plan + confidence summary
GET  /v1/regulatory/reports/{report_id}/narrative   # plain markdown
GET  /v1/regulatory/reports/{report_id}/citations   # full inline citation table
POST /v1/regulatory/reports/{report_id}/rerender    # rebuild at a new page budget

POST /v1/ip/jobs                              # 202 + job_id, IP discovery + report
GET  /v1/ip/jobs/{job_id}                     # IP job status + summary
GET  /v1/ip/reports/{report_id}               # IP layout plan + portfolio summary
GET  /v1/ip/reports/{report_id}/narrative     # IP markdown narrative
GET  /v1/ip/reports/{report_id}/citations     # IP citation table (patent / tribunal)
GET  /v1/ip/reports/{report_id}/findings      # ranked IPFinding list
GET  /v1/ip/companies/{company_id}/families   # patent families with framework scores
POST /v1/ip/reports/{report_id}/rerender      # rerun at a different page budget

GET  /health
```

## IP Intelligence Engine

```
Company request
  → IP source adapters (USPTO, PatentsView, Google Patents, EPO,
    USPTO Assignments, PTAB, litigation)
  → document registry (same dedupe + audit as regulatory)
  → rule-based IP extraction (claim parsing, classification, breadth)
  → family construction (parent-pointer + heuristic clustering)
  → verification (VERIFIED / REPORTED / INFERRED per family)
  → six-framework scoring per family:
      claim strength, moat, commercialization, differentiation,
      FTO risk, portfolio quality, exclusivity, strategic value
  → cross-framework signal score + signal/noise filter
  → finding builder (5 categories × 1 finding/family on high signal,
    1 table-only stub on low signal)
  → adaptive 5→7→8 page layout (expand on omitted_high_signal > 10%
    or omitted critical FTO findings)
  → IP narrative renderer (Claude Opus 4.7 in prod; stub in CI)
  → persisted IPReportRunRow + citations table + REST endpoints
```

### Five-page architecture

```
1. IP Executive Summary                  (220-300 words)
2. Portfolio Architecture                (200-280 words)
3. Claim Strength and Moat               (220-300 words)
4. Commercial and Competitive Implications (200-280 words)
5. Key Risks and FTO                     (200-280 words)
```

Adaptive expansion appends overflow into the section with the largest
remaining high-signal pool — soft cap 7 pages, hard cap 8.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # add ".[dev,llm]" to enable real LLM calls
cp .env.example .env               # then edit MEDFUEL_CONTACT_EMAIL / MEDFUEL_USER_AGENT
pytest
uvicorn medfuel.main:app --reload
```

Default datastore is SQLite (`./medfuel.sqlite`); set
`MEDFUEL_DATABASE_URL` to a Postgres or Supabase URL to switch.
Set `MEDFUEL_USE_LLM=1` plus the relevant API keys to swap the
deterministic stubs for OpenAI Structured Outputs extraction and
Anthropic Claude narrative generation.

## Source-rank ordering (drives signal scoring)

| Rank | Sources |
| ---- | ------- |
| 1    | FDA, EMA, MHRA, PMDA |
| 2    | ClinicalTrials.gov, SEC, USPTO, PubMed |
| 4    | Company websites |
| 5    | Investor decks |

Regulator records outrank company claims; verification confidence
escalates whenever at least one official-rank document supports an event.

## Layout

```
src/medfuel/
  config.py             env-driven settings
  models/
    schemas.py          CompanyIdentity, RawSourceRecord, SourceType...
    extraction.py       CandidateEvent, RegulatoryEvent, VerifiedClaim, ReportPlan
  db/                   SQLAlchemy ORM + registry + audit stream
  http/client.py        RateLimitedClient + per-host RateLimiter
  adapters/             one adapter per regulatory source
  llm/                  LLM client abstraction; OpenAI / Anthropic / Stub impls
  extract/              rule + LLM extractors, normalize, dedupe, orchestrator
  verify/               regulatory verifier + citation engine
  score/                regulatory signal score
  render/               regulatory layout + narrative + report builder
  ingest/pipeline.py    regulatory fan-out discovery + chained Phase 2/3
  api/routes.py         /v1/regulatory routes
  ip/                   IP Intelligence Engine (Phase 4)
    models.py             PatentFamily, PatentClaim, IPFinding, FrameworkScores
    db_orm.py             IP-side persistence tables (shared Base)
    adapters/             PatentsView, Google Patents, EPO, USPTO Assignments,
                          PTAB, litigation, USPTOAdapter passthrough
    extract/              claim parser, family builder, rule extractor, orchestrator
    verify/               VERIFIED / REPORTED / INFERRED classifier
    score/                six framework scorers + signal score + noise filter
    render/               5-page IP layout, findings builder, narrative, citations,
                          end-to-end IPReportBuilder
    ingest/pipeline.py    IP discovery pipeline (parallel adapter fan-out)
    api/routes.py         /v1/ip routes
  main.py               create_app() with lifespan init_db
tests/                  pytest + respx + in-memory SQLite, 75 tests
  ip/                     IP-side tests (frameworks, claim parser, family builder,
                          layout, verifier, end-to-end pipeline, API)
```

## Operator notes

- SEC + NCBI both expect a contact email in the `User-Agent` / `From`
  header; `MEDFUEL_CONTACT_EMAIL` is wired into both.
- Without `MEDFUEL_FIRECRAWL_API_KEY`, the MHRA/PMDA/company-web
  adapters degrade to no-ops (pipeline still runs).
- Without `MEDFUEL_USE_LLM=1`, the rule-based extractor handles all
  structured sources and a deterministic narrator produces the
  templated report.
- Adapter failures never abort the pipeline — captured per-adapter as
  error strings in `DiscoveryResult.errors` and recorded on the
  `JobRow`.
- Every insert / duplicate-skip / status transition emits an
  `audit_events` row keyed by `entity_type` + `entity_id`.

## Open questions (carried from the design doc)

- **Model naming**: public OpenAI docs do not currently list
  `gpt-5.5-mini`; the default `MEDFUEL_EXTRACTION_MODEL` is therefore
  `gpt-5.4-mini`. Set the env var to an internal alias if your
  deployment exposes one.
- **PMDA/MHRA depth**: both are workable but page-centric. Expand
  the Firecrawl crawl plans before promoting beyond search-result
  ingestion.
- **Scope boundary**: EudraCT, national EU portals, CMS/reimbursement,
  litigation dockets are out of scope for the first release and
  belong in a follow-on expansion phase.
