import Link from 'next/link'
import type { RunSummary } from '@/lib/types/run'

type Props = { runs: RunSummary[] }

function DecisionBadge({ decision }: { decision: string }) {
  const lower = decision.toLowerCase()
  if (lower === 'buy')  return <span className="badge-buy">{decision}</span>
  if (lower === 'sell') return <span className="badge-sell">{decision}</span>
  if (lower === 'hold') return <span className="badge-hold">{decision}</span>
  return (
    <span
      className="px-2.5 py-1 rounded-full text-[10px] font-bold"
      style={{
        fontFamily: 'var(--font-mono)',
        letterSpacing: '0.08em',
        background: 'var(--bg-elevated)',
        color: 'var(--text-mid)',
        border: '1px solid var(--border-raised)',
      }}
    >
      {decision}
    </span>
  )
}

function StatusDot({ decision }: { decision?: string }) {
  const lower = decision?.toLowerCase()
  const color = lower === 'buy' ? 'var(--buy)' : lower === 'sell' ? 'var(--sell)' : lower === 'hold' ? 'var(--hold)' : 'var(--text-low)'
  return (
    <div
      className="w-1.5 h-1.5 rounded-full shrink-0"
      style={{ background: color, boxShadow: decision ? `0 0 5px ${color}80` : 'none' }}
    />
  )
}

export default function RunHistoryTable({ runs }: Props) {
  if (runs.length === 0) {
    return (
      <div
        className="rounded-2xl flex flex-col items-center justify-center py-20 gap-4"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
      >
        {/* Empty state icon */}
        <div
          className="w-14 h-14 rounded-2xl flex items-center justify-center"
          style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-raised)' }}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <rect x="3" y="3" width="18" height="4" rx="2" fill="var(--text-low)"/>
            <rect x="3" y="10" width="12" height="4" rx="2" fill="var(--text-low)" opacity=".6"/>
            <rect x="3" y="17" width="15" height="4" rx="2" fill="var(--text-low)" opacity=".4"/>
          </svg>
        </div>
        <div className="text-center">
          <p
            className="text-sm font-medium mb-1"
            style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-manrope)' }}
          >
            No analysis runs yet
          </p>
          <p className="text-xs" style={{ color: 'var(--text-low)' }}>
            Start your first analysis to see results here
          </p>
        </div>
        <Link href="/new-run" className="btn-primary mt-2">
          <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
            <polygon points="2.5,2 9,5.5 2.5,9" fill="currentColor"/>
          </svg>
          New Analysis
        </Link>
      </div>
    )
  }

  return (
    <div
      className="overflow-hidden"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: '14px',
      }}
    >
      {/* Table header */}
      <div
        className="grid gap-0"
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr 100px 160px 80px',
          background: 'var(--bg-elevated)',
          borderBottom: '1px solid var(--border)',
          padding: '0 20px',
        }}
      >
        {['Ticker', 'Date', 'Decision', 'Created', ''].map((h) => (
          <div
            key={h}
            className="apex-label py-3"
          >
            {h}
          </div>
        ))}
      </div>

      {/* Rows */}
      <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
        {runs.map((run, idx) => (
          <div
            key={run.id}
            className="group transition-colors duration-100 animate-fade-up"
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr 100px 160px 80px',
              padding: '0 20px',
              alignItems: 'center',
              animationDelay: `${idx * 30}ms`,
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-hover)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = '')}
          >
            {/* Ticker */}
            <div className="py-4 flex items-center gap-2.5">
              <StatusDot decision={run.decision} />
              <span
                className="terminal-text font-bold text-sm tracking-wider"
                style={{ color: 'var(--text-high)' }}
              >
                {run.ticker}
              </span>
            </div>

            {/* Date */}
            <div
              className="py-4 terminal-text text-sm"
              style={{ color: 'var(--text-mid)', letterSpacing: '0.02em' }}
            >
              {run.date}
            </div>

            {/* Decision */}
            <div className="py-4">
              {run.decision ? (
                <DecisionBadge decision={run.decision} />
              ) : (
                <span
                  className="text-xs font-bold"
                  style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-low)', letterSpacing: '0.08em' }}
                >
                  PENDING
                </span>
              )}
            </div>

            {/* Created */}
            <div
              className="py-4 text-xs terminal-text"
              style={{ color: 'var(--text-low)', letterSpacing: '0.02em' }}
            >
              {new Date(run.created_at).toLocaleString()}
            </div>

            {/* Action */}
            <div className="py-4">
              <Link
                href={`/runs/${run.id}`}
                className="inline-flex items-center gap-1.5 text-xs font-semibold transition-all duration-150 opacity-0 group-hover:opacity-100"
                style={{
                  color: 'var(--accent)',
                  fontFamily: 'var(--font-manrope)',
                  letterSpacing: '0.02em',
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--accent-light)' }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--accent)' }}
              >
                View
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <path d="M2.5 6h7M6.5 3l3 3-3 3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </Link>
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div
        className="px-5 py-3 flex items-center justify-between"
        style={{ borderTop: '1px solid var(--border)', background: 'var(--bg-elevated)' }}
      >
        <span
          className="text-[10px] font-bold"
          style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-low)', letterSpacing: '0.1em' }}
        >
          {runs.length} RUN{runs.length !== 1 ? 'S' : ''} TOTAL
        </span>
        <span
          className="text-[10px]"
          style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-low)', letterSpacing: '0.06em' }}
        >
          TRADINGAGENTS · LOCAL
        </span>
      </div>
    </div>
  )
}
