'use client';

import { useEffect, useState } from 'react';
import { clinicalEvidenceApi } from '../api';
import type { CompanyContext, RunState, SectionPayload } from '../types';

interface State {
  run: RunState | null;
  payload: SectionPayload | null;
  error: string | null;
}

export function useSectionRun(company: CompanyContext | null, runIdOverride?: string) {
  const [state, setState] = useState<State>({ run: null, payload: null, error: null });

  useEffect(() => {
    if (!company && !runIdOverride) return;
    let cancelled = false;

    async function go() {
      try {
        let run: RunState;
        if (runIdOverride) {
          run = await clinicalEvidenceApi.getRun(runIdOverride);
        } else if (company) {
          run = await clinicalEvidenceApi.startRun(company);
        } else {
          return;
        }
        if (cancelled) return;
        setState({ run, payload: null, error: null });

        while (!cancelled) {
          run = await clinicalEvidenceApi.getRun(run.run_id);
          if (cancelled) return;
          setState((s) => ({ ...s, run }));
          if (run.status === 'ready') {
            const payload = await clinicalEvidenceApi.getPayload(run.run_id);
            if (cancelled) return;
            setState({ run, payload, error: null });
            return;
          }
          if (run.status === 'failed') {
            setState({ run, payload: null, error: run.error ?? 'run failed' });
            return;
          }
          await new Promise((r) => setTimeout(r, 1500));
        }
      } catch (e) {
        if (!cancelled) {
          setState((s) => ({ ...s, error: (e as Error).message }));
        }
      }
    }

    void go();
    return () => {
      cancelled = true;
    };
  }, [company?.company_id, company?.name, runIdOverride]);

  return state;
}
