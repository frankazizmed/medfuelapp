import type { VerificationStatus } from '../../types';

const styles = {
  VERIFIED: 'bg-signal-600 text-white',
  REPORTED: 'bg-ink-100 text-ink-600',
  INFERRED: 'bg-risk-50 text-risk-600 border border-risk-600',
} as const;

export function ConfidenceBadge({ status }: { status: VerificationStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-[0.12em] ${styles[status]}`}
    >
      {status}
    </span>
  );
}
