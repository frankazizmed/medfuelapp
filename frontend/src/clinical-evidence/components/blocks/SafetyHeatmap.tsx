import type { SafetyHeatmapBlock as Block } from '../../types';
import { CiteRefs } from './CiteRefs';

const severityScale = {
  mild: { color: 'bg-ink-100', dot: 'bg-ink-400' },
  moderate: { color: 'bg-risk-50', dot: 'bg-risk-400' },
  severe: { color: 'bg-risk-50', dot: 'bg-risk-600' },
  sae: { color: 'bg-risk-600 text-white', dot: 'bg-white' },
} as const;

export function SafetyHeatmap({ block }: { block: Block }) {
  return (
    <div>
      <h3 className="mb-2 text-[10px] uppercase tracking-[0.18em] text-ink-400">{block.title}</h3>
      <div className="overflow-hidden rounded border border-rule">
        <table className="w-full table-fixed border-collapse text-[11.5px]">
          <thead>
            <tr className="border-b border-rule bg-ink-50 text-left text-[10px] uppercase tracking-[0.12em] text-ink-400">
              <th className="w-[58%] px-2 py-1.5 font-medium">Event</th>
              <th className="w-[16%] px-2 py-1.5 font-medium">Severity</th>
              <th className="w-[12%] px-2 py-1.5 font-medium">Tx rate</th>
              <th className="w-[10%] px-2 py-1.5 font-medium">Ctrl</th>
              <th className="w-[4%] px-2 py-1.5 font-medium" />
            </tr>
          </thead>
          <tbody>
            {block.rows.map((r, i) => {
              const s = severityScale[r.severity];
              return (
                <tr key={i} className={`border-b border-rule last:border-0 ${s.color}`}>
                  <td className="px-2 py-1.5 font-serif">{r.event}</td>
                  <td className="px-2 py-1.5">
                    <span className="inline-flex items-center gap-1.5">
                      <span className={`h-2 w-2 rounded-full ${s.dot}`} />
                      <span className="text-[10px] uppercase tracking-[0.12em]">{r.severity}</span>
                    </span>
                  </td>
                  <td className="px-2 py-1.5 font-mono tabular-nums">
                    {r.rate_treatment != null ? `${r.rate_treatment}` : '—'}
                  </td>
                  <td className="px-2 py-1.5 font-mono tabular-nums">
                    {r.rate_control != null ? `${r.rate_control}` : '—'}
                  </td>
                  <td className="px-2 py-1.5">
                    <CiteRefs nums={r.citation_numbers} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
