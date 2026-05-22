import React from 'react';

interface Props {
  index: number;
  title: string;
  total: number;
  companyName: string;
  children: React.ReactNode;
}

export function Page({ index, title, total, companyName, children }: Props) {
  return (
    <section
      data-page={index}
      className="ce-page mx-auto mb-8 flex h-[297mm] w-[210mm] flex-col bg-white px-[18mm] py-[16mm] shadow-sm print:m-0 print:h-[297mm] print:w-[210mm] print:break-after-page print:shadow-none"
    >
      <header className="flex items-baseline justify-between border-b border-rule pb-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-ink-400">
            MedFuel · Clinical Evidence
          </div>
          <h1 className="mt-1 font-serif text-[22px] leading-tight text-ink-900">{title}</h1>
        </div>
        <div className="text-right text-[10px] uppercase tracking-[0.18em] text-ink-400">
          <div>{companyName}</div>
          <div>
            Page <span className="font-mono text-ink-600">{index}</span> / {total}
          </div>
        </div>
      </header>
      <div className="flex-1 overflow-hidden pt-5">
        <div className="ce-content space-y-5">{children}</div>
      </div>
      <footer className="border-t border-rule pt-2 text-[9px] uppercase tracking-[0.18em] text-ink-400">
        Institutional Clinical Evidence Diligence · For authorized recipients
      </footer>
    </section>
  );
}
