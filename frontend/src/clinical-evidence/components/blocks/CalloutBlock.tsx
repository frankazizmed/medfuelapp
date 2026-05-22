import type { CalloutBlock as Block } from '../../types';
import { CiteRefs } from './CiteRefs';

const toneStyles = {
  signal: 'border-l-signal-600 bg-signal-50',
  risk: 'border-l-risk-600 bg-risk-50',
  neutral: 'border-l-ink-400 bg-ink-50',
} as const;

const toneLabel = {
  signal: 'Signal',
  risk: 'Risk',
  neutral: 'Note',
} as const;

export function CalloutBlock({ block }: { block: Block }) {
  return (
    <div className={`border-l-4 ${toneStyles[block.tone]} px-3 py-2`}>
      <div className="text-[10px] uppercase tracking-[0.18em] text-ink-400">
        {toneLabel[block.tone]} · <span className="text-ink-600">{block.title}</span>
      </div>
      <div className="mt-1 font-serif text-[12.5px] leading-snug text-ink-800">
        {block.text}
        <CiteRefs nums={block.citation_numbers} />
      </div>
    </div>
  );
}
