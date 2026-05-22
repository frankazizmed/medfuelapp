import type { EvidenceHierarchyBlock as Block } from '../../types';
import { CiteRefs } from './CiteRefs';
import { ConfidenceBadge } from './ConfidenceBadge';

export function EvidenceHierarchy({ block }: { block: Block }) {
  const max = Math.max(0.001, ...block.entries.map((e) => e.weight));
  return (
    <div>
      <h3 className="mb-2 text-[10px] uppercase tracking-[0.18em] text-ink-400">{block.title}</h3>
      <div className="space-y-1.5">
        {block.entries.map((e, i) => {
          const pct = Math.max(4, Math.round((e.weight / max) * 100));
          return (
            <div key={i} className="grid grid-cols-[110px_1fr_auto_auto] items-center gap-3">
              <div className="font-serif text-[12px] text-ink-800">{e.label}</div>
              <div className="h-2 overflow-hidden rounded bg-ink-100">
                <div className="h-full bg-ink-600" style={{ width: `${pct}%` }} />
              </div>
              <ConfidenceBadge status={e.verification} />
              <div className="flex items-center gap-1">
                <span className="font-mono text-[10px] text-ink-400 tabular-nums">
                  {e.weight.toFixed(2)}
                </span>
                <CiteRefs nums={e.citation_numbers} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
