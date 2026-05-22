import type { TrialTimelineBlock as Block } from '../../types';
import { CiteRefs } from './CiteRefs';

const phaseColor = {
  phase4: 'bg-signal-600',
  phase3: 'bg-signal-400',
  phase2_3: 'bg-ink-600',
  phase2: 'bg-ink-400',
  phase1_2: 'bg-ink-200',
  phase1: 'bg-ink-200',
  preclinical: 'bg-ink-100',
  unknown: 'bg-ink-100',
} as const;

export function TrialTimeline({ block }: { block: Block }) {
  return (
    <div>
      <h3 className="mb-2 text-[10px] uppercase tracking-[0.18em] text-ink-400">{block.title}</h3>
      <div className="space-y-1.5">
        {block.entries.map((e, i) => (
          <div key={i} className="flex items-center gap-3 rounded border border-rule px-2 py-1.5">
            <span
              className={`inline-flex h-5 items-center rounded px-2 text-[10px] font-medium uppercase tracking-[0.08em] text-white ${phaseColor[e.phase]}`}
            >
              {e.phase}
            </span>
            <div className="flex-1 font-serif text-[12px] leading-tight text-ink-800">{e.label}</div>
            <div className="font-mono text-[10px] text-ink-400 tabular-nums">
              {e.start ?? '—'} → {e.end ?? '—'}
            </div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-ink-600">{e.status ?? ''}</div>
            <CiteRefs nums={e.citation_numbers} />
          </div>
        ))}
      </div>
    </div>
  );
}
