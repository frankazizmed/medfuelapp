'use client';

import { clinicalEvidenceApi } from '../api';

export function ExportPdfButton({ runId }: { runId: string }) {
  async function onClick() {
    const res = await fetch(clinicalEvidenceApi.exportPdfUrl(runId), { method: 'POST' });
    if (!res.ok) {
      alert(`PDF export failed: ${res.status} ${await res.text()}`);
      return;
    }
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `clinical-evidence-${runId}.pdf`;
    a.click();
    URL.revokeObjectURL(a.href);
  }
  return (
    <button
      type="button"
      onClick={onClick}
      className="no-print rounded border border-ink-200 bg-white px-3 py-1.5 text-[11px] uppercase tracking-[0.12em] text-ink-800 hover:bg-ink-50"
    >
      Export PDF
    </button>
  );
}
