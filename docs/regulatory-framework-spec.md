# Regulatory Framework — Port Spec for the Web App Report Section

This is an implementation-ready, language-agnostic specification of the
regulatory analysis framework built in `frankazizmed/medfuelapp` (Python).
Paste this into a session scoped to `medfuel/medfuel-web-app` to reimplement
the logic inside a report section (e.g. a "Regulatory" section) in Node/TypeScript.

It is the *methodology*, not the Python code — no Python is reused. Wire the
inputs from whatever the web app already has (its own source fetchers / DB).

---

## 0. Pipeline order (what the section does)

```
collected source documents
  → extract candidate events
  → normalize (dates, agency names, asset aliases)
  → dedupe by semantic event key
  → verify (assign confidence + state from source authority)
  → score (signal 0–100)
  → NOISE GATE (tier each claim; drop/keep/table)  ← the heart
  → layout (place into sections, expand pages only if warranted)
  → render section text with inline citations
```

The noise gate is the part that makes the section feel "institutional"
rather than a data dump. Implement it faithfully.

---

## 1. Core types

```ts
type EventType =
  | "approval" | "clearance" | "designation" | "clinical_hold"
  | "warning" | "inspection" | "label_change" | "trial_update"
  | "patent_event" | "offering_or_filing" | "manufacturing_issue";

type SourceType =
  | "fda" | "ema" | "mhra" | "pmda" | "clinicaltrials"
  | "sec" | "uspto" | "pubmed" | "company" | "investor_deck";

interface RegulatoryEvent {
  eventId: string;
  agency: string;            // canonical: "FDA","EMA","MHRA","PMDA","SEC","USPTO","ClinicalTrials.gov"
  jurisdiction: string;      // "US","EU","UK","JP","GLOBAL"
  eventType: EventType;
  status: string;
  eventDate: string;         // ISO date
  summary: string;
  assetName?: string;
  investorImportance: number; // 1..5
  evidenceStrength: number;   // 1..5
  sourceDocIds: string[];     // ids of supporting documents
}

interface VerifiedClaim {
  claimId: string;
  eventId: string;
  text: string;
  verificationState: "verified" | "partially_verified" | "reported_only" | "rejected";
  confidence: "high" | "medium" | "low";
  sourceDocIds: string[];
  signalScore: number;       // 0..100
  citationNumbers: number[]; // assigned at render time
}
```

---

## 2. Source authority ranking (drives everything downstream)

`officialRank`: **lower = more authoritative**.

| Rank | Sources |
| ---- | ------- |
| 1 | FDA, EMA, MHRA, PMDA |
| 2 | ClinicalTrials.gov, SEC, USPTO, PubMed |
| 4 | Company website |
| 5 | Investor deck |

Rule: **regulator records outrank company claims** whenever they conflict.
"Official" = rank ≤ 2. "Company/deck" = rank ≥ 4.

---

## 3. Signal score (exact formula)

```
signalScore = round(100 * (
    0.30 * relevance
  + 0.30 * (evidenceStrength / 5)
  + 0.15 * uniqueness
  + 0.25 * (investorImportance / 5)
), 2)
```

Sub-scores:

- **relevance**: `patent_event → 0.5`; critical type → `0.9`; everything else → `0.7`.
- **uniqueness**: `min(0.4 + 0.2 * nSources, 0.9)` where `nSources = max(sourceDocIds.length, 1)`.
- **evidence/investor**: the 1–5 inputs divided by 5.

**Critical event types** (used by relevance AND the noise gate):
`approval, clinical_hold, warning, inspection, label_change, manufacturing_issue`.

---

## 4. Verification confidence (from source authority)

Given the claim's supporting docs and their ranks:

```
officialCount = count(sourceDocIds where rank <= 2)
total         = sourceDocIds.length

officialCount >= 1            → confidence "high",   state "verified"
else total >= 2               → confidence "medium", state "partially_verified"
else                          → confidence "low",    state "reported_only"
```

(One official source is enough for high confidence; two non-official
corroborating sources give medium.)

---

## 5. NOISE GATE — fluff-elimination rules (the important part)

Run these **in order** over the scored claims. Record a reason for every drop
so the section can show "what was filtered and why".

**Tier outcomes:** `must_include` | `narrative` | `table_only` | `dropped`.

1. **Orphan / no citation** → `dropped` ("no_citation"). Any claim with zero
   `sourceDocIds` is removed. Nothing ships uncited.
2. **Stale** → `dropped` ("stale_gt_max_age"). If `eventDate` is older than
   **10 years**, drop it — UNLESS its type anchors current exclusivity /
   labeling / platform credibility: `approval, designation, patent_event,
   label_change` (those are kept regardless of age).
3. **Cosmetic duplicate** → keep one, `dropped` ("cosmetic_duplicate") for the
   rest. Group surviving claims by a normalized summary key
   (`lowercase`, strip non-alphanumerics, collapse whitespace). Within a group
   keep the highest `(signalScore, evidenceStrength)`; drop the others.
4. **Score-band tiering:**
   - `>= 85` → `must_include`
   - `75–84` → `narrative`
   - `55–74` → `table_only` (supporting tables only, never prose)
   - `< 55`  → `dropped` ("below_threshold"), **except** critical types, which
     are demoted to `table_only` for chronology/contradiction safety.
5. **Company/deck share cap (15%):** a claim is "company-only" if ALL its
   sources have rank ≥ 4. If company-only claims exceed **15%** of the
   `must_include + narrative` set, demote the lowest-scoring company-only ones
   to `table_only` until ≤ 15%. (Management framing can never dominate.)

Final buckets:
- **narrative** = `must_include` ∪ `narrative`
- **table** = `table_only`
- Everything else is excluded from the section entirely.

Emit a small breakdown for auditing: `{input, must_include, narrative,
table_only, dropped, company_demoted, dropped_reasons{...}}`.

---

## 6. Section structure (4-page aim) + word budgets

Four sections. Word budgets are targets, enforced by the writer prompt.

| # | slug | title | words | themes (event types it pulls) |
|---|------|-------|------:|-------------------------------|
| 1 | `executive_summary` | Executive summary | 280–340 | synthesis (all) |
| 2 | `pathway_and_timeline` | Pathway and timeline | 260–340 | approval, clearance, designation, offering_or_filing, patent_event |
| 3 | `trials_safety_compliance` | Trials, safety and compliance | 320–420 | trial_update, clinical_hold, warning, inspection, label_change, manufacturing_issue |
| 4 | `implications_and_watchlist` | Implications and watchlist | 220–300 | synthesis (all) |

Placement caps per section: synthesis sections take the top **6** narrative
claims; themed sections take the top **3**; table bucket takes up to **6**.
Rank candidates by `(signalScore desc, eventDate desc)`. A claim is placed once.

---

## 7. Pagination / adaptive expansion

- **Aim = 4 pages. Max = 8.** Four is the target, not a cap.
- After filling the 4 baseline sections, expand **+1 page at a time** while
  EITHER trigger holds:
  - `omittedCritical > 0` (a critical-type narrative claim didn't get placed), OR
  - `omittedHighSignalShare > 0.10` (>10% of claims scoring ≥ 75 are unplaced).
- Each expansion adds up to 3 more high-signal claims into the section with the
  most unplaced themed claims. Stop when both triggers clear or at 8 pages.
- Expansion metrics count **narrative-eligible** claims only — table-only
  context never counts as "omitted".

---

## 8. Writer prompt contract (for the LLM that drafts the section)

Feed the writer ONLY:
- the placed verified claims (narrative + table buckets, with their citation numbers),
- the per-section word budget,
- the banned-fluff rules (no adjectives without a verifiable fact; no restating
  standard regulatory process unless it changes timing/risk; every sentence must
  map to ≥1 citation).

Never feed it raw low-signal/ dropped claims. The writer summarizes; it does not
discover. Render table-only claims as a compact supporting list, not prose.

---

## 9. Reference implementation (TypeScript sketch)

```ts
const CRITICAL = new Set<EventType>([
  "approval","clinical_hold","warning","inspection","label_change","manufacturing_issue",
]);
const STALE_ANCHORS = new Set<EventType>([
  "approval","designation","patent_event","label_change",
]);

export function signalScore(e: RegulatoryEvent): number {
  const relevance = e.eventType === "patent_event" ? 0.5 : CRITICAL.has(e.eventType) ? 0.9 : 0.7;
  const n = Math.max(e.sourceDocIds.length, 1);
  const uniqueness = Math.min(0.4 + 0.2 * n, 0.9);
  const raw =
    0.30 * relevance +
    0.30 * (e.evidenceStrength / 5) +
    0.15 * uniqueness +
    0.25 * (e.investorImportance / 5);
  return Math.round(100 * raw * 100) / 100;
}

type Tier = "must_include" | "narrative" | "table_only" | "dropped";

export function noiseGate(
  claims: VerifiedClaim[],
  events: Map<string, RegulatoryEvent>,
  docRank: (sourceDocId: string) => number,
  asOf = new Date(),
): { tier: Map<string, Tier>; dropped: [string, string][] } {
  const tier = new Map<string, Tier>();
  const dropped: [string, string][] = [];
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

  // 1 + 2: no-citation and stale
  let surviving = claims.filter((c) => {
    const e = events.get(c.eventId)!;
    if (c.sourceDocIds.length === 0) { tier.set(c.claimId, "dropped"); dropped.push([c.claimId, "no_citation"]); return false; }
    const ageYears = (asOf.getTime() - new Date(e.eventDate).getTime()) / (365.25 * 864e5);
    if (ageYears > 10 && !STALE_ANCHORS.has(e.eventType)) { tier.set(c.claimId, "dropped"); dropped.push([c.claimId, "stale_gt_max_age"]); return false; }
    return true;
  });

  // 3: cosmetic-duplicate suppression
  const groups = new Map<string, VerifiedClaim[]>();
  for (const c of surviving) {
    const k = norm(events.get(c.eventId)!.summary);
    (groups.get(k) ?? groups.set(k, []).get(k)!).push(c);
  }
  const deduped: VerifiedClaim[] = [];
  for (const g of groups.values()) {
    g.sort((a, b) => b.signalScore - a.signalScore || events.get(b.eventId)!.evidenceStrength - events.get(a.eventId)!.evidenceStrength);
    deduped.push(g[0]);
    g.slice(1).forEach((c) => { tier.set(c.claimId, "dropped"); dropped.push([c.claimId, "cosmetic_duplicate"]); });
  }

  // 4: score bands
  for (const c of deduped) {
    const e = events.get(c.eventId)!;
    if (c.signalScore >= 85) tier.set(c.claimId, "must_include");
    else if (c.signalScore >= 75) tier.set(c.claimId, "narrative");
    else if (c.signalScore >= 55) tier.set(c.claimId, "table_only");
    else if (CRITICAL.has(e.eventType)) tier.set(c.claimId, "table_only");
    else { tier.set(c.claimId, "dropped"); dropped.push([c.claimId, "below_threshold"]); }
  }

  // 5: company/deck 15% cap
  const isCompanyOnly = (c: VerifiedClaim) => c.sourceDocIds.every((s) => docRank(s) >= 4);
  const narrative = deduped.filter((c) => tier.get(c.claimId) === "must_include" || tier.get(c.claimId) === "narrative");
  const companyNarr = narrative.filter(isCompanyOnly).sort((a, b) => a.signalScore - b.signalScore);
  if (narrative.length) {
    const allowed = Math.floor(0.15 * narrative.length);
    for (const c of companyNarr.slice(0, Math.max(0, companyNarr.length - allowed))) tier.set(c.claimId, "table_only");
  }
  return { tier, dropped };
}
```

---

## 10. Acceptance checks to port too

- Every placed claim resolves to ≥ 1 citation (fail the render otherwise).
- A sub-55 non-critical claim never appears in prose.
- A company-only-sourced narrative cannot exceed 15% of narrative claims.
- A claim with an official (rank ≤ 2) source is "high" confidence.
- Default render = 4 pages; expansion only on the two triggers; hard cap 8.

---

*Source of truth for these numbers: `frankazizmed/medfuelapp` — `score/signal.py`,
`score/noise.py`, `render/sections.py`, `render/layout.py`, `verify/verifier.py`,
`models/schemas.py` (OFFICIAL_RANK).*
