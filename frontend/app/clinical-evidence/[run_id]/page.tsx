'use client';

import { use } from 'react';
import { ClinicalEvidenceSection } from '@/clinical-evidence';

interface Props {
  params: Promise<{ run_id: string }>;
}

export default function Page({ params }: Props) {
  const { run_id } = use(params);
  return (
    <main className="mx-auto max-w-[230mm] px-4 py-8">
      <header className="no-print mb-4">
        <div className="text-[10px] uppercase tracking-[0.18em] text-ink-400">MedFuel · Diligence</div>
        <h1 className="font-serif text-2xl text-ink-900">Clinical Evidence Section</h1>
        <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em] text-ink-400">Run {run_id}</div>
      </header>
      <ClinicalEvidenceSection runId={run_id} />
    </main>
  );
}
