'use client';

import { useMemo } from 'react';
import { useSectionRun } from './hooks/useSectionRun';
import type { CompanyContext } from './types';
import { SectionRenderer } from './components/SectionRenderer';
import { ExportPdfButton } from './components/ExportPdfButton';

interface Props {
  /** Either provide a CompanyContext to start a new run … */
  company?: CompanyContext;
  /** … or pass an existing run_id to attach to an in-flight or completed run. */
  runId?: string;
}

const STATUS_LABEL: Record<string, string> = {
  queued: 'Queued',
  discovering: 'Discovering trials, publications, filings…',
  ingesting: 'Ingesting documents…',
  extracting: 'Extracting clinical findings…',
  verifying: 'Cross-source verification…',
  scoring: 'Scoring clinical signal…',
  generating: 'Generating institutional narrative…',
  laying_out: 'Composing pages…',
  ready: 'Ready',
  failed: 'Failed',
};

export function ClinicalEvidenceSection({ company, runId }: Props) {
  const company_normalized = useMemo(() => company ?? null, [company?.company_id, company?.name]);
  const { run, payload, error } = useSectionRun(company_normalized, runId);

  if (error) {
    return (
      <div className="rounded border border-risk-600 bg-risk-50 px-4 py-3 text-[12px] text-risk-600">
        Clinical Evidence pipeline failed: {error}
      </div>
    );
  }

  if (!payload) {
    return (
      <div className="rounded border border-ink-200 bg-white px-4 py-6 text-center font-mono text-[12px] uppercase tracking-[0.12em] text-ink-600">
        {run ? STATUS_LABEL[run.status] ?? run.status : 'Starting…'}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="no-print flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-[0.12em] text-ink-400">
          {payload.page_count} pages · {payload.citations.length} citations ·
          {' '}omitted high-signal {Math.round(payload.omitted_high_signal_fraction * 100)}%
          {payload.expanded_from_default && ' · expanded'}
        </div>
        <ExportPdfButton runId={payload.run_id} />
      </div>
      <SectionRenderer payload={payload} />
    </div>
  );
}

export type { CompanyContext, SectionPayload } from './types';
