'use client'
import { use, useEffect, useState } from 'react'
import { useRunStream } from '@/features/run-detail/hooks/useRunStream'
import PipelineStepper from '@/features/run-detail/components/PipelineStepper'
import VerdictBanner from '@/features/run-detail/components/VerdictBanner'
import PhaseTabs from '@/features/run-detail/components/PhaseTabs'
import { getRun } from '@/lib/api-client'
import type { RunSummary } from '@/lib/types/run'

const STATUS_CONFIG: Record<string, {
  bg: string; color: string; dot: string; label: string; pulse: boolean
}> = {
  connecting: { bg: 'var(--bg-elevated)',     color: 'var(--text-mid)',  dot: 'var(--text-low)',  label: 'Connecting',  pulse: false },
  running:    { bg: 'var(--hold-bg)',          color: 'var(--hold)',      dot: 'var(--hold)',      label: 'Running',     pulse: true  },
  complete:   { bg: 'var(--buy-bg)',           color: 'var(--buy)',       dot: 'var(--buy)',       label: 'Complete',    pulse: false },
  error:      { bg: 'var(--error-bg)',         color: 'var(--error)',     dot: 'var(--error)',     label: 'Error',       pulse: false },
}

export default function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const { steps, reports, verdict, status, error } = useRunStream(id)
  const [run, setRun] = useState<RunSummary | null>(null)

  useEffect(() => {
    getRun(id).then(setRun).catch(() => {})
  }, [id])

  const sc = STATUS_CONFIG[status] ?? STATUS_CONFIG.connecting

  return (
    <div className="max-w-4xl space-y-4 animate-fade-up">

      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-2">
        <div>
          <div className="apex-label mb-3" style={{ color: 'var(--accent)', opacity: 0.7 }}>
            Analysis Run
          </div>
          <h1
            className="flex items-baseline gap-3"
            style={{
              fontFamily: 'var(--font-syne)',
              fontSize: '32px',
              fontWeight: 800,
              letterSpacing: '-0.04em',
              lineHeight: 1.1,
            }}
          >
            {run ? (
              <>
                <span
                  className="terminal-text"
                  style={{ color: 'var(--accent-light)', fontFamily: 'var(--font-mono)', fontWeight: 700, letterSpacing: '0.04em' }}
                >
                  {run.ticker}
                </span>
                <span style={{ color: 'var(--text-low)', fontWeight: 400, fontFamily: 'var(--font-manrope)' }}>·</span>
                <span style={{ color: 'var(--text-mid)', fontSize: '22px', fontFamily: 'var(--font-mono)', fontWeight: 500 }}>
                  {run.date}
                </span>
              </>
            ) : (
              <span style={{ color: 'var(--text-mid)', fontSize: '24px' }}>Loading…</span>
            )}
          </h1>
        </div>

        {/* Status pill */}
        <div
          className="flex items-center gap-2 px-3.5 py-1.5 rounded-full text-[10px] font-bold mt-1.5 shrink-0"
          style={{
            background: sc.bg,
            color: sc.color,
            border: `1px solid ${sc.dot}40`,
            fontFamily: 'var(--font-mono)',
            letterSpacing: '0.1em',
          }}
        >
          <div
            className="w-1.5 h-1.5 rounded-full shrink-0"
            style={{
              background: sc.dot,
              boxShadow: sc.pulse ? `0 0 6px ${sc.dot}` : 'none',
              animation: sc.pulse ? 'shimmer 1s ease-in-out infinite' : 'none',
            }}
          />
          {sc.label.toUpperCase()}
        </div>
      </div>

      {/* Pipeline */}
      <PipelineStepper steps={steps} />

      {/* Error */}
      {error && (
        <div
          className="px-4 py-3 rounded-xl text-sm flex items-center gap-2"
          style={{
            background: 'var(--error-bg)',
            color: 'var(--error)',
            border: '1px solid rgba(255,43,62,0.25)',
          }}
        >
          <span className="font-bold">Error:</span> {error}
        </div>
      )}

      {/* Verdict */}
      {verdict && run && (
        <VerdictBanner verdict={verdict} ticker={run.ticker} date={run.date} />
      )}

      {/* Phase tabs + reports */}
      <PhaseTabs steps={steps} reports={reports} />
    </div>
  )
}
