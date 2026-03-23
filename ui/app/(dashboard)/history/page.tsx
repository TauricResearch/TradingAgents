'use client'
import Link from 'next/link'
import { useRunHistory } from '@/features/history/hooks/useRunHistory'
import RunHistoryTable from '@/features/history/components/RunHistoryTable'

export default function HistoryPage() {
  const { runs, loading, error } = useRunHistory()

  return (
    <div className="max-w-4xl animate-fade-up">
      {/* Header */}
      <div className="flex items-end justify-between mb-8 gap-4">
        <div>
          <div className="apex-label mb-3" style={{ color: 'var(--accent)', opacity: 0.7 }}>
            Execution Log
          </div>
          <h1
            style={{
              fontFamily: 'var(--font-syne)',
              fontSize: '32px',
              fontWeight: 800,
              letterSpacing: '-0.04em',
              color: 'var(--text-high)',
              lineHeight: 1.1,
              marginBottom: '8px',
            }}
          >
            Run History
          </h1>
          <p className="text-sm" style={{ color: 'var(--text-mid)' }}>
            Comprehensive log of all agent execution cycles
          </p>
        </div>

        <Link href="/new-run" className="btn-primary shrink-0">
          <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
            <polygon points="2.5,2 9,5.5 2.5,9" fill="var(--bg-base)"/>
          </svg>
          New Analysis
        </Link>
      </div>

      {loading && (
        <div className="flex items-center gap-2.5 py-8" style={{ color: 'var(--text-mid)' }}>
          <div
            className="w-2 h-2 rounded-full"
            style={{ background: 'var(--accent)', animation: 'shimmer 1s infinite' }}
          />
          <span className="text-sm" style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', letterSpacing: '0.04em' }}>
            Loading runs…
          </span>
        </div>
      )}

      {error && (
        <div
          className="px-4 py-3 rounded-xl text-sm"
          style={{
            background: 'var(--error-bg)',
            color: 'var(--error)',
            border: '1px solid rgba(255,43,62,0.25)',
          }}
        >
          {error}
        </div>
      )}

      {!loading && <RunHistoryTable runs={runs} />}
    </div>
  )
}
