'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

export default function Home() {
  const [name, setName] = useState('');
  const [tickers, setTickers] = useState('');
  const [assets, setAssets] = useState('');
  const [indications, setIndications] = useState('');
  const router = useRouter();

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    const company_id = `co-${name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 40)}-${Date.now().toString(36)}`;
    const params = new URLSearchParams({
      company_id,
      name: name.trim(),
      tickers: tickers.trim(),
      assets: assets.trim(),
      indications: indications.trim(),
    });
    router.push(`/clinical-evidence/run?${params.toString()}`);
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <div className="mb-8">
        <div className="text-[10px] uppercase tracking-[0.18em] text-ink-400">MedFuel</div>
        <h1 className="mt-1 font-serif text-3xl text-ink-900">Clinical Evidence Intelligence Engine</h1>
        <p className="mt-3 max-w-xl font-serif text-[14px] leading-relaxed text-ink-600">
          Enter a public biotech and the engine will discover registered trials,
          publications, FDA/EMA records, and SEC filings; extract structured findings;
          rank signal vs noise; and render a six-page institutional clinical evidence section.
        </p>
      </div>

      <form onSubmit={onSubmit} className="space-y-3 rounded border border-rule bg-white p-5">
        <label className="block">
          <span className="text-[10px] uppercase tracking-[0.18em] text-ink-400">Company name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Acme Therapeutics"
            className="mt-1 block w-full rounded border border-ink-200 px-3 py-2 font-serif text-[13px] focus:border-ink-600 focus:outline-none"
            required
          />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-[10px] uppercase tracking-[0.18em] text-ink-400">Tickers (comma-sep)</span>
            <input
              value={tickers}
              onChange={(e) => setTickers(e.target.value)}
              placeholder="ACME"
              className="mt-1 block w-full rounded border border-ink-200 px-3 py-2 font-serif text-[13px]"
            />
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-[0.18em] text-ink-400">Assets (comma-sep)</span>
            <input
              value={assets}
              onChange={(e) => setAssets(e.target.value)}
              placeholder="acme-101"
              className="mt-1 block w-full rounded border border-ink-200 px-3 py-2 font-serif text-[13px]"
            />
          </label>
        </div>
        <label className="block">
          <span className="text-[10px] uppercase tracking-[0.18em] text-ink-400">Indications (comma-sep)</span>
          <input
            value={indications}
            onChange={(e) => setIndications(e.target.value)}
            placeholder="heart failure"
            className="mt-1 block w-full rounded border border-ink-200 px-3 py-2 font-serif text-[13px]"
          />
        </label>
        <div className="flex justify-end pt-2">
          <button
            type="submit"
            className="rounded bg-ink-800 px-5 py-2 text-[11px] uppercase tracking-[0.18em] text-white hover:bg-ink-900"
          >
            Generate clinical evidence section
          </button>
        </div>
      </form>
    </main>
  );
}
