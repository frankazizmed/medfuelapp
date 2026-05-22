import type { EndpointTableBlock as Block } from '../../types';
import { CiteRefs } from './CiteRefs';
import { StatSigIndicator } from './StatSigIndicator';

const endpointTypeStyles = {
  hard: 'bg-signal-50 text-signal-600',
  composite: 'bg-ink-100 text-ink-800',
  surrogate: 'bg-risk-50 text-risk-600',
  unknown: 'bg-ink-100 text-ink-400',
} as const;

export function EndpointTable({ block }: { block: Block }) {
  return (
    <div>
      <h3 className="mb-2 text-[10px] uppercase tracking-[0.18em] text-ink-400">{block.title}</h3>
      <div className="overflow-hidden rounded border border-rule">
        <table className="w-full table-fixed border-collapse text-[11.5px]">
          <thead>
            <tr className="border-b border-rule bg-ink-50 text-left text-[10px] uppercase tracking-[0.12em] text-ink-400">
              <th className="w-[42%] px-2 py-1.5 font-medium">Endpoint</th>
              <th className="w-[14%] px-2 py-1.5 font-medium">Type</th>
              <th className="w-[18%] px-2 py-1.5 font-medium">Result</th>
              <th className="w-[14%] px-2 py-1.5 font-medium">Stat sig</th>
              <th className="w-[8%] px-2 py-1.5 font-medium">N</th>
              <th className="w-[4%] px-2 py-1.5 font-medium" />
            </tr>
          </thead>
          <tbody>
            {block.rows.map((r, i) => (
              <tr key={i} className="border-b border-rule last:border-0">
                <td className="px-2 py-1.5 font-serif text-ink-800">{r.endpoint}</td>
                <td className="px-2 py-1.5">
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] ${endpointTypeStyles[r.endpoint_type]}`}
                  >
                    {r.endpoint_type}
                  </span>
                </td>
                <td className="px-2 py-1.5 font-mono text-ink-800 tabular-nums">{r.result ?? '—'}</td>
                <td className="px-2 py-1.5">
                  <StatSigIndicator p={r.p_value} />
                </td>
                <td className="px-2 py-1.5 font-mono text-ink-600 tabular-nums">{r.n ?? '—'}</td>
                <td className="px-2 py-1.5">
                  <CiteRefs nums={r.citation_numbers} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
