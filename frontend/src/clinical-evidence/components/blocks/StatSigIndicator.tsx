export function StatSigIndicator({ p }: { p?: number | null }) {
  if (p == null) return <span className="text-ink-400">—</span>;
  let band: 'high' | 'mid' | 'low' | 'ns';
  if (p < 0.001) band = 'high';
  else if (p < 0.01) band = 'mid';
  else if (p < 0.05) band = 'low';
  else band = 'ns';
  const styles = {
    high: 'bg-signal-600 text-white',
    mid: 'bg-signal-400 text-white',
    low: 'bg-signal-50 text-signal-600',
    ns: 'bg-ink-100 text-ink-600',
  } as const;
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] tabular-nums ${styles[band]}`}
    >
      p={p < 0.001 ? '<0.001' : p.toFixed(p < 0.01 ? 3 : 2)}
    </span>
  );
}
