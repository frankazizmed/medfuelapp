import type { ParagraphBlock as Block } from '../../types';
import { CiteRefs } from './CiteRefs';

export function ParagraphBlock({ block }: { block: Block }) {
  return (
    <p className="font-serif text-[13px] leading-[1.55] text-ink-800">
      {block.text}
      <CiteRefs nums={block.citation_numbers} />
    </p>
  );
}
