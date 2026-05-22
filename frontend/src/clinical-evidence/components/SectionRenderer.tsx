import type { Page, PageBlock, SectionPayload } from '../types';
import { Page as PageComponent } from './Page';
import { CalloutBlock } from './blocks/CalloutBlock';
import { CitationsPanel } from './blocks/CitationsPanel';
import { EndpointTable } from './blocks/EndpointTable';
import { EvidenceHierarchy } from './blocks/EvidenceHierarchy';
import { HeadingBlock } from './blocks/HeadingBlock';
import { ParagraphBlock } from './blocks/ParagraphBlock';
import { SafetyHeatmap } from './blocks/SafetyHeatmap';
import { TrialTimeline } from './blocks/TrialTimeline';

function renderBlock(block: PageBlock, idx: number): React.ReactNode {
  switch (block.kind) {
    case 'paragraph':
      return <ParagraphBlock key={idx} block={block} />;
    case 'heading':
      return <HeadingBlock key={idx} block={block} />;
    case 'callout':
      return <CalloutBlock key={idx} block={block} />;
    case 'endpoint_table':
      return <EndpointTable key={idx} block={block} />;
    case 'safety_heatmap':
      return <SafetyHeatmap key={idx} block={block} />;
    case 'trial_timeline':
      return <TrialTimeline key={idx} block={block} />;
    case 'evidence_hierarchy':
      return <EvidenceHierarchy key={idx} block={block} />;
    default:
      return null;
  }
}

interface Props {
  payload: SectionPayload;
}

export function SectionRenderer({ payload }: Props) {
  return (
    <div className="print:m-0">
      {payload.pages.map((p: Page) => (
        <PageComponent
          key={p.index}
          index={p.index}
          title={p.title}
          total={payload.page_count}
          companyName={payload.company_name}
        >
          {p.blocks.map((b, i) => renderBlock(b, i))}
          {p.index === payload.page_count && <CitationsPanel citations={payload.citations} />}
        </PageComponent>
      ))}
    </div>
  );
}
