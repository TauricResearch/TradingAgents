'use client'
import { use, useEffect, useState } from 'react'
import { useRunStream } from '@/features/run-detail/hooks/useRunStream'
import PipelineStepper from '@/features/run-detail/components/PipelineStepper'
import VerdictBanner from '@/features/run-detail/components/VerdictBanner'
import PhaseTabs from '@/features/run-detail/components/PhaseTabs'
import { getRun } from '@/lib/api-client'
import type { RunSummary } from '@/lib/types/run'

const STATUS_CONFIG: Record<string, { bg: string; color: string; dot: string; label: string }> = {
  connecting: { bg: 'var(--bg-elevated)',     color: 'var(--text-mid)',      dot: 'var(--text-low)',      label: 'Connecting'  },
  running:    { bg: 'var(--hold-bg)',          color: 'var(--hold)',          dot: 'var(--hold)',          label: 'Running'     },
  complete:   { bg: 'var(--buy-bg)',           color: 'var(--buy)',           dot: 'var(--buy)',           label: 'Complete'    },
  error:      { bg: 'var(--error-bg)',         color: 'var(--error)',         dot: 'var(--error)',         label: 'Error'       },
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
      <div className="flex items-start justify-between gap-4">
        <div>
          <div
            className="apex-label mb-2"
          >
            Analysis Run
          </div>
          <h1
            className="text-[26px] font-bold tracking-tight"
            style={{
              color:       'var(--text-high)',
              fontFamily:  'var(--font-manrope)',
              letterSpacing: '-0.03em',
            }}
          >
            {run ? (
              <>
                <span style={{ color: 'var(--accent-light)' }}>{run.ticker}</span>
                <span style={{ color: 'var(--text-low)', fontWeight: 400, margin: '0 8px' }}>·</span>
                <span>{run.date}</span>
              </>
            ) : (
              <span style={{ color: 'var(--text-mid)' }}>Loading…</span>
            )}
          </h1>
        </div>

        {/* Status badge */}
        <div
          className="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium mt-1"
          style={{
            background:  sc.bg,
            color:       sc.color,
            border:      `1px solid ${sc.dot}40`,
            fontFamily:  'var(--font-manrope)',
          }}
        >
          <div
            className="w-1.5 h-1.5 rounded-full shrink-0"
            style={{
              background: sc.dot,
              animation:  status === 'running' ? 'shimmer 1.2s ease-in-out infinite' : 'none',
            }}
          />
          {sc.label}
        </div>
      </div>

      {/* Pipeline */}
      <PipelineStepper steps={steps} />

      {/* Error */}
      {error && (
        <div
          className="px-4 py-3 rounded-lg text-sm"
          style={{
            background: 'var(--error-bg)',
            color:      'var(--error)',
            border:     '1px solid rgba(255,68,68,0.25)',
          }}
        >
          <span className="font-medium">Error:</span> {error}
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
