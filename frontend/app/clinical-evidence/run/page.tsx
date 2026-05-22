'use client';

import { useSearchParams } from 'next/navigation';
import { Suspense, useMemo } from 'react';
import { ClinicalEvidenceSection } from '@/clinical-evidence';
import type { CompanyContext } from '@/clinical-evidence';

function Inner() {
  const sp = useSearchParams();
  const company = useMemo<CompanyContext | undefined>(() => {
    const name = sp.get('name');
    const company_id = sp.get('company_id');
    if (!name || !company_id) return undefined;
    const split = (s: string | null) =>
      (s ?? '')
        .split(',')
        .map((x) => x.trim())
        .filter(Boolean);
    return {
      company_id,
      name,
      tickers: split(sp.get('tickers')),
      assets: split(sp.get('assets')),
      indications: split(sp.get('indications')),
    };
  }, [sp]);

  if (!company) {
    return (
      <div className="mx-auto max-w-2xl p-8 text-[12px] text-ink-600">
        Missing company parameters. Go back to the home page.
      </div>
    );
  }

  return (
    <main className="mx-auto max-w-[230mm] px-4 py-8">
      <header className="no-print mb-4 flex items-baseline justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-ink-400">MedFuel · Diligence</div>
          <h1 className="font-serif text-2xl text-ink-900">{company.name}</h1>
        </div>
        <div className="text-[10px] uppercase tracking-[0.18em] text-ink-400">Clinical Evidence Section</div>
      </header>
      <ClinicalEvidenceSection company={company} />
    </main>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div className="p-8 text-[12px] text-ink-600">Loading…</div>}>
      <Inner />
    </Suspense>
  );
}
