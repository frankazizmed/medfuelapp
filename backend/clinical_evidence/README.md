# Clinical Evidence — MedFuel Diligence Island

Self-contained module that produces the **Clinical Evidence** section of a
MedFuel diligence report. Each section in MedFuel is built as an isolated
"island"; this one owns its own routes, schemas, DB tables (`ce_*`), and
config (`CE_*`).

## Mounting

```python
import clinical_evidence

app = FastAPI()
app.include_router(clinical_evidence.router)
```

```tsx
import { ClinicalEvidenceSection } from '@/clinical-evidence';

<ClinicalEvidenceSection company={{ company_id, name, tickers, assets, indications }} />
```

## Pipeline (per run)

1. **Discovery** — ClinicalTrials.gov, PubMed, openFDA, EMA, SEC EDGAR, Tavily
2. **Ingestion** — Firecrawl + PyMuPDF + heading-aware normalizer
3. **Extraction** — OpenAI structured outputs → `ClinicalFinding[]`
4. **Verification** — cross-source reconciliation → `VERIFIED / REPORTED / INFERRED`
5. **Signal** — 9-dimension scoring + risk flags + aggressive noise removal
6. **Narrative** — Claude (page-by-page, prompt-cached system block) +
   deterministic fallback composer
7. **Layout** — adaptive 6→10 page budget
8. **Citations** — numbered, confidence-tagged source list

## Output

A `SectionPayload` — 6..10 typed pages, each containing typed `PageBlock`s
(endpoint tables, safety heatmaps, callouts, trial timelines, evidence
hierarchies, paragraphs). The frontend renders these print-ready;
`POST /clinical-evidence/{run_id}/pdf` exports via Playwright Chromium.

## Tests

```bash
cd backend && PYTHONPATH=. pytest clinical_evidence/tests/
```
