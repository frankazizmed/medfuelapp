import React from 'react';

export function CiteRefs({ nums }: { nums?: number[] }) {
  if (!nums || nums.length === 0) return null;
  return (
    <sup className="ml-1 font-mono text-[10px] text-ink-400">
      {nums.map((n, i) => (
        <span key={n}>
          {i > 0 ? ',' : ''}
          {n}
        </span>
      ))}
    </sup>
  );
}
