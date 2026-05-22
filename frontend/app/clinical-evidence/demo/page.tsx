import { SectionRenderer } from '@/clinical-evidence/components/SectionRenderer';
import type { SectionPayload } from '@/clinical-evidence/types';
import payload from '@/clinical-evidence/fixtures.demo.json';

export const dynamic = 'force-static';

export default function DemoPage() {
  const typed = payload as unknown as SectionPayload;
  return (
    <main className="mx-auto max-w-[230mm] px-4 py-8">
      <header className="no-print mb-4">
        <div className="text-[10px] uppercase tracking-[0.18em] text-ink-400">MedFuel · Diligence (demo)</div>
        <h1 className="font-serif text-2xl text-ink-900">{typed.company_name}</h1>
        <div className="mt-1 text-[10px] uppercase tracking-[0.12em] text-ink-400">
          {typed.page_count} pages · {typed.citations.length} citations · expanded {String(typed.expanded_from_default)}
        </div>
      </header>
      <SectionRenderer payload={typed} />
    </main>
  );
}
