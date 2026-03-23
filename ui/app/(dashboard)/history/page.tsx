'use client'
import Link from 'next/link'
import { useRunHistory } from '@/features/history/hooks/useRunHistory'
import RunHistoryTable from '@/features/history/components/RunHistoryTable'

export default function HistoryPage() {
  const { runs, loading, error } = useRunHistory()
  return (
    <div className="max-w-4xl animate-fade-up">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1
            className="text-2xl font-bold mb-1"
            style={{ color: 'var(--text-high)', fontFamily: 'var(--font-manrope)' }}
          >
            Run History
          </h1>
          <p className="text-sm" style={{ color: 'var(--text-mid)' }}>
            Comprehensive log of all agent execution cycles
          </p>
        </div>
        <Link href="/new-run" className="btn-primary px-5 py-2.5 text-sm">
          + New Analysis
        </Link>
      </div>

      {loading && (
        <p className="text-sm" style={{ color: 'var(--text-mid)' }}>
          Loading...
        </p>
      )}
      {error && (
        <p className="text-sm" style={{ color: 'var(--error)' }}>
          {error}
        </p>
      )}
      {!loading && <RunHistoryTable runs={runs} />}
    </div>
  )
}
