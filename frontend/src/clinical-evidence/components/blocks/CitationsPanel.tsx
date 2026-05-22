import type { Citation } from '../../types';

const sourceLabels: Record<string, string> = {
  clinicaltrials: 'CT.gov',
  pubmed: 'PubMed',
  fda: 'FDA',
  ema: 'EMA',
  sec: 'SEC',
  company_web: 'Company',
  investor_deck: 'IR deck',
  conference: 'Conference',
  press_release: 'Press',
  preprint: 'Preprint',
  other: 'Other',
};

export function CitationsPanel({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return (
      <div className="text-[11px] text-ink-400">
        No external sources cited in this snapshot.
      </div>
    );
  }
  return (
    <div>
      <h3 className="mb-2 text-[10px] uppercase tracking-[0.18em] text-ink-400">Citations</h3>
      <ol className="space-y-1">
        {citations.map((c) => (
          <li key={c.number} className="grid grid-cols-[28px_56px_1fr_60px_60px] items-baseline gap-2 text-[11px]">
            <span className="font-mono text-ink-400">[{c.number}]</span>
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-600">
              {sourceLabels[c.source] ?? c.source}
            </span>
            <a className="font-serif text-ink-800 underline decoration-ink-200" href={c.url} target="_blank" rel="noreferrer">
              {c.title ?? c.url}
            </a>
            <span className="font-mono text-[10px] tabular-nums text-ink-400">
              conf {c.confidence.toFixed(2)}
            </span>
            <span className="font-mono text-[10px] tabular-nums text-ink-400">
              evid {c.evidence_strength.toFixed(2)}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
