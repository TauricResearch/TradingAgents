import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ReportSection } from '../types';

const DECISION_COLORS: Record<string, string> = {
  Buy:         'var(--green)',
  Overweight:  'var(--teal)',
  Hold:        'var(--amber)',
  Underweight: 'var(--orange)',
  Sell:        'var(--red)',
};

const BORDER_COLORS: Record<string, string> = {
  market_report:          'var(--green)',
  sentiment_report:       'var(--blue)',
  news_report:            'var(--blue)',
  fundamentals_report:    'var(--accent)',
  investment_plan:        'var(--amber)',
  trader_investment_plan: 'var(--red)',
  final_trade_decision:   'var(--green)',
};

interface Props {
  sections: ReportSection[];
  decision: string | null;
}

export default function ReportFeed({ sections, decision }: Props) {
  if (sections.length === 0 && !decision) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-muted)' }}>
        Run an analysis to see results here.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {sections.map((s) => (
        <div key={s.section} style={{
          background: 'var(--bg-card)',
          borderRadius: 8,
          borderLeft: `3px solid ${BORDER_COLORS[s.section] ?? 'var(--accent)'}`,
          overflow: 'hidden',
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '10px 16px', borderBottom: '1px solid var(--border)',
            background: 'rgba(255,255,255,0.02)',
          }}>
            <span style={{ fontWeight: 700, fontSize: 13 }}>{s.title}</span>
            <span style={{
              fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 10,
              background: 'rgba(16,185,129,0.15)', color: 'var(--green)',
            }}>Completed</span>
          </div>
          <div style={{ padding: '14px 16px', fontSize: 13, lineHeight: 1.7, color: 'var(--text-secondary)' }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{s.content}</ReactMarkdown>
          </div>
        </div>
      ))}

      {decision && (
        <div style={{
          padding: '16px 20px', borderRadius: 8, textAlign: 'center',
          background: `${DECISION_COLORS[decision] ?? 'var(--accent)'}22`,
          border: `1px solid ${DECISION_COLORS[decision] ?? 'var(--accent)'}`,
          fontSize: 18, fontWeight: 700,
          color: DECISION_COLORS[decision] ?? 'var(--text-primary)',
        }}>
          Final Decision: {decision}
        </div>
      )}
    </div>
  );
}
