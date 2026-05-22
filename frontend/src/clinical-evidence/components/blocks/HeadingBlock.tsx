import type { HeadingBlock as Block } from '../../types';

export function HeadingBlock({ block }: { block: Block }) {
  if ((block.level ?? 2) <= 1) {
    return null; // Page header already renders the top-level title.
  }
  return (
    <h2 className="mt-4 font-serif text-[16px] font-semibold tracking-tight text-ink-900">
      {block.text}
    </h2>
  );
}
