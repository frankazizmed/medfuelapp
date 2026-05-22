// Mirror of backend SectionPayload. Hand-typed to avoid build-time codegen
// coupling. Backend Pydantic schema is the source of truth — see
// backend/clinical_evidence/schemas.py.

export type VerificationStatus = 'VERIFIED' | 'REPORTED' | 'INFERRED';

export type EndpointType = 'hard' | 'surrogate' | 'composite' | 'unknown';

export type TrialPhase =
  | 'preclinical'
  | 'phase1'
  | 'phase1_2'
  | 'phase2'
  | 'phase2_3'
  | 'phase3'
  | 'phase4'
  | 'unknown';

export type SourceKind =
  | 'clinicaltrials'
  | 'pubmed'
  | 'fda'
  | 'ema'
  | 'sec'
  | 'company_web'
  | 'investor_deck'
  | 'conference'
  | 'press_release'
  | 'preprint'
  | 'other';

export interface Citation {
  number: number;
  doc_id: string;
  url: string;
  title?: string | null;
  source: SourceKind;
  confidence: number;
  evidence_strength: number;
}

export interface ParagraphBlock {
  kind: 'paragraph';
  text: string;
  citation_numbers?: number[];
}

export interface HeadingBlock {
  kind: 'heading';
  text: string;
  level?: number;
  citation_numbers?: number[];
}

export interface CalloutBlock {
  kind: 'callout';
  tone: 'signal' | 'risk' | 'neutral';
  title: string;
  text: string;
  citation_numbers?: number[];
}

export interface EndpointTableRow {
  endpoint: string;
  endpoint_type: EndpointType;
  arm?: string | null;
  result?: string | null;
  p_value?: number | null;
  ci?: string | null;
  n?: number | null;
  citation_numbers?: number[];
}

export interface EndpointTableBlock {
  kind: 'endpoint_table';
  title: string;
  rows: EndpointTableRow[];
  citation_numbers?: number[];
}

export interface SafetyHeatmapRow {
  event: string;
  rate_treatment?: number | null;
  rate_control?: number | null;
  severity: 'mild' | 'moderate' | 'severe' | 'sae';
  citation_numbers?: number[];
}

export interface SafetyHeatmapBlock {
  kind: 'safety_heatmap';
  title: string;
  rows: SafetyHeatmapRow[];
  citation_numbers?: number[];
}

export interface TrialTimelineEntry {
  label: string;
  phase: TrialPhase;
  start?: string | null;
  end?: string | null;
  status?: string | null;
  citation_numbers?: number[];
}

export interface TrialTimelineBlock {
  kind: 'trial_timeline';
  title: string;
  entries: TrialTimelineEntry[];
  citation_numbers?: number[];
}

export interface EvidenceHierarchyEntry {
  label: string;
  weight: number;
  verification: VerificationStatus;
  citation_numbers?: number[];
}

export interface EvidenceHierarchyBlock {
  kind: 'evidence_hierarchy';
  title: string;
  entries: EvidenceHierarchyEntry[];
  citation_numbers?: number[];
}

export type PageBlock =
  | ParagraphBlock
  | HeadingBlock
  | CalloutBlock
  | EndpointTableBlock
  | SafetyHeatmapBlock
  | TrialTimelineBlock
  | EvidenceHierarchyBlock;

export interface Page {
  index: number;
  title: string;
  blocks: PageBlock[];
}

export interface SectionPayload {
  run_id: string;
  company_id: string;
  company_name: string;
  pages: Page[];
  citations: Citation[];
  page_count: number;
  expanded_from_default: boolean;
  omitted_high_signal_fraction: number;
  generated_at: string;
  model_versions: Record<string, string>;
}

export type RunStatus =
  | 'queued'
  | 'discovering'
  | 'ingesting'
  | 'extracting'
  | 'verifying'
  | 'scoring'
  | 'generating'
  | 'laying_out'
  | 'ready'
  | 'failed';

export interface RunState {
  run_id: string;
  company_id: string;
  status: RunStatus;
  started_at: string;
  updated_at: string;
  error?: string | null;
}

export interface CompanyContext {
  company_id: string;
  name: string;
  tickers?: string[];
  indications?: string[];
  assets?: string[];
}
