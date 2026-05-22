import type { CompanyContext, RunState, SectionPayload } from './types';

const BASE = '/api/clinical-evidence';

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  }
  return (await res.json()) as T;
}

export const clinicalEvidenceApi = {
  startRun: (company: CompanyContext) =>
    jsonFetch<RunState>(`${BASE}/run`, { method: 'POST', body: JSON.stringify(company) }),
  getRun: (runId: string) => jsonFetch<RunState>(`${BASE}/${runId}`),
  getPayload: (runId: string) => jsonFetch<SectionPayload>(`${BASE}/${runId}/payload`),
  exportPdfUrl: (runId: string) => `${BASE}/${runId}/pdf`,
};
