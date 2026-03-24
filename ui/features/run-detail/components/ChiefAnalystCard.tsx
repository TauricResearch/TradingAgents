'use client'
import { useState } from 'react'
import { usePDF } from 'react-to-pdf'
import type { ChiefAnalystReport } from '@/lib/types/agents'
import type { StepStatus } from '@/lib/types/agents'

type Props = {
  report: ChiefAnalystReport | null
  status: StepStatus
  ticker: string
  date: string
}

const VERDICT_COLOR: Record<string, string> = {
  BUY:  'var(--buy)',
  SELL: 'var(--sell)',
  HOLD: 'var(--hold)',
}

export default function ChiefAnalystCard({ report, status, ticker, date }: Props) {
  const [pdfError, setPdfError] = useState(false)
  const { toPDF, targetRef } = usePDF({ filename: `${ticker}-${date}-chief-analyst-report.pdf` })

  const handleDownload = () => {
    setPdfError(false)
    try { toPDF() } catch { setPdfError(true) }
  }

  return (
    <div
      data-testid="chief-analyst-card"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: '14px',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-6 py-4"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '10px',
            fontWeight: 700,
            letterSpacing: '0.12em',
            color: 'var(--accent)',
            textTransform: 'uppercase',
            opacity: 0.8,
          }}
        >
          Chief Analyst — Executive Summary
        </div>

        {status === 'done' && report && (
          <div className="flex items-center gap-3">
            {pdfError && (
              <span style={{ fontSize: '11px', color: 'var(--error)', fontFamily: 'var(--font-mono)' }}>
                PDF failed — try again
              </span>
            )}
            <button
              onClick={handleDownload}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-bold transition-all duration-150"
              style={{
                background: 'var(--accent-glow)',
                color: 'var(--accent)',
                border: '1px solid var(--accent-dim)',
                fontFamily: 'var(--font-mono)',
                letterSpacing: '0.06em',
                cursor: 'pointer',
              }}
            >
              ↓ Download PDF
            </button>
          </div>
        )}
      </div>

      {/* Body */}
      {status === 'pending' && (
        <div
          className="px-6 py-8 flex items-center gap-3"
          style={{ color: 'var(--text-low)', fontFamily: 'var(--font-mono)', fontSize: '12px', letterSpacing: '0.04em' }}
        >
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: 'var(--text-faint)' }}
          />
          Chief Analyst is standing by…
        </div>
      )}

      {status === 'running' && (
        <div className="px-6 py-6 space-y-3">
          {[40, 70, 55, 80].map((w, i) => (
            <div
              key={i}
              className="h-3 rounded-full"
              style={{
                width: `${w}%`,
                background: 'var(--bg-elevated)',
                animation: 'shimmer 1.2s ease-in-out infinite',
                animationDelay: `${i * 0.15}s`,
              }}
            />
          ))}
        </div>
      )}

      {status === 'done' && !report && (
        <div
          className="px-6 py-8"
          style={{ color: 'var(--text-low)', fontFamily: 'var(--font-mono)', fontSize: '12px' }}
        >
          Report unavailable for this run.
        </div>
      )}

      {status === 'done' && report && (
        <div ref={targetRef} className="px-6 py-5 space-y-5">
          {/* Top row: Verdict + Catalyst */}
          <div className="grid grid-cols-[auto,1fr] gap-6 items-start">
            {/* Verdict badge */}
            <div className="flex flex-col items-center gap-1.5">
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '9px',
                  letterSpacing: '0.1em',
                  color: 'var(--text-low)',
                  textTransform: 'uppercase',
                }}
              >
                Verdict
              </div>
              <div
                className="px-5 py-2 rounded-xl font-bold"
                style={{
                  fontFamily: 'var(--font-syne)',
                  fontSize: '24px',
                  letterSpacing: '-0.02em',
                  color: VERDICT_COLOR[report.verdict] ?? 'var(--text-high)',
                  border: `2px solid ${VERDICT_COLOR[report.verdict] ?? 'var(--border)'}`,
                  background: 'var(--bg-elevated)',
                  boxShadow: `0 0 20px ${VERDICT_COLOR[report.verdict] ?? 'transparent'}20`,
                }}
              >
                {report.verdict}
              </div>
            </div>

            {/* Catalyst */}
            <div>
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '9px',
                  letterSpacing: '0.1em',
                  color: 'var(--text-low)',
                  textTransform: 'uppercase',
                  marginBottom: '6px',
                }}
              >
                Catalyst
              </div>
              <p style={{ fontFamily: 'var(--font-manrope)', fontSize: '13px', color: 'var(--text-high)', lineHeight: 1.6 }}>
                {report.catalyst}
              </p>
            </div>
          </div>

          {/* Divider */}
          <div style={{ height: '1px', background: 'var(--border)' }} />

          {/* Execution */}
          <div>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '9px',
                letterSpacing: '0.1em',
                color: 'var(--text-low)',
                textTransform: 'uppercase',
                marginBottom: '6px',
              }}
            >
              Execution
            </div>
            <p style={{ fontFamily: 'var(--font-manrope)', fontSize: '13px', color: 'var(--text-mid)', lineHeight: 1.6 }}>
              {report.execution}
            </p>
          </div>

          {/* Divider */}
          <div style={{ height: '1px', background: 'var(--border)' }} />

          {/* Tail Risk */}
          <div>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '9px',
                letterSpacing: '0.1em',
                color: 'var(--sell)',
                opacity: 0.8,
                textTransform: 'uppercase',
                marginBottom: '6px',
              }}
            >
              Tail Risk
            </div>
            <p style={{ fontFamily: 'var(--font-manrope)', fontSize: '13px', color: 'var(--text-mid)', lineHeight: 1.6 }}>
              {report.tail_risk}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
