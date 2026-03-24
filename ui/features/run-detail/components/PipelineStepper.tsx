import { AGENT_STEPS, STEP_PHASE } from '@/lib/types/run'
import type { AgentStep } from '@/lib/types/run'
import type { StepStatus } from '@/lib/types/agents'

type Phase = 'analysts' | 'researchers' | 'trader' | 'risk' | 'summary'
type Props = { steps: Record<string, StepStatus> }

const PHASES: Phase[] = ['analysts', 'researchers', 'trader', 'risk', 'summary']

const PHASE_META: Record<Phase, { label: string; code: string; desc: string }> = {
  analysts:    { label: 'Analysis',      code: 'PHASE-01', desc: 'Market data & signals'   },
  researchers: { label: 'Research',      code: 'PHASE-02', desc: 'Bull/bear debate'         },
  trader:      { label: 'Trade Plan',    code: 'PHASE-03', desc: 'Strategy formulation'     },
  risk:        { label: 'Risk Review',   code: 'PHASE-04', desc: 'Risk-adjusted decision'   },
  summary:     { label: 'Chief Analyst', code: 'PHASE-05', desc: 'Executive synthesis'      },
}

function phaseStatus(phase: Phase, steps: Record<string, StepStatus>): StepStatus {
  const phaseSteps = AGENT_STEPS.filter((s) => STEP_PHASE[s as AgentStep] === phase)
  if (phaseSteps.every((s) => steps[s] === 'done')) return 'done'
  if (phaseSteps.some((s) => steps[s] === 'running')) return 'running'
  return 'pending'
}

export default function PipelineStepper({ steps }: Props) {
  const doneCount = PHASES.filter((p) => phaseStatus(p, steps) === 'done').length
  const progressPct = (doneCount / PHASES.length) * 100

  return (
    <div
      className="relative overflow-hidden"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: '14px',
        padding: '20px 24px',
      }}
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-5">
        <div className="apex-label">Agent Pipeline</div>
        <div
          className="flex items-center gap-2"
          style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-mid)', letterSpacing: '0.06em' }}
        >
          <span style={{ color: 'var(--accent)' }}>{doneCount}</span>
          <span style={{ color: 'var(--text-low)' }}>/</span>
          <span>{PHASES.length}</span>
          <span style={{ color: 'var(--text-low)', marginLeft: 4 }}>PHASES</span>
        </div>
      </div>

      {/* Progress track */}
      <div
        className="relative h-1 rounded-full mb-6 overflow-hidden"
        style={{ background: 'var(--border-raised)' }}
      >
        <div
          className="absolute left-0 top-0 h-full rounded-full transition-all duration-700"
          style={{
            width: `${progressPct}%`,
            background: 'linear-gradient(90deg, var(--accent-dim), var(--accent))',
            boxShadow: '0 0 8px var(--accent-glow)',
          }}
        >
          {/* Moving glow tip */}
          {progressPct > 0 && progressPct < 100 && (
            <div
              className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 rounded-full"
              style={{
                background: 'var(--accent)',
                boxShadow: '0 0 8px var(--accent)',
                animation: 'pulse-glow 1.5s ease-in-out infinite',
              }}
            />
          )}
        </div>

        {/* Scanline on active */}
        {doneCount < PHASES.length && (
          <div
            className="absolute inset-y-0 w-12"
            style={{
              background: 'linear-gradient(90deg, transparent, rgba(0,196,232,0.4), transparent)',
              animation: 'scan-line 2s ease-in-out infinite',
            }}
          />
        )}
      </div>

      {/* Phase nodes */}
      <div className="grid grid-cols-5 gap-2">
        {PHASES.map((phase, i) => {
          const status    = phaseStatus(phase, steps)
          const isDone    = status === 'done'
          const isRunning = status === 'running'
          const meta      = PHASE_META[phase]

          return (
            <div
              key={phase}
              className="relative flex flex-col items-center gap-2.5 p-3 rounded-xl transition-all duration-300"
              style={{
                background: isDone
                  ? 'rgba(0,196,232,0.06)'
                  : isRunning
                    ? 'rgba(255,180,0,0.06)'
                    : 'var(--bg-elevated)',
                border: isDone
                  ? '1px solid rgba(0,196,232,0.20)'
                  : isRunning
                    ? '1px solid rgba(255,180,0,0.25)'
                    : '1px solid var(--border)',
              }}
            >
              {/* Node circle */}
              <div
                className="relative w-10 h-10 rounded-full flex items-center justify-center transition-all duration-500"
                style={{
                  background: isDone
                    ? 'var(--accent)'
                    : isRunning
                      ? 'var(--bg-hover)'
                      : 'var(--bg-elevated)',
                  border: isDone
                    ? '2px solid var(--accent)'
                    : isRunning
                      ? '2px solid var(--status-running)'
                      : '1px solid var(--border-raised)',
                  boxShadow: isDone
                    ? '0 0 20px rgba(0,196,232,0.35)'
                    : isRunning
                      ? '0 0 16px rgba(255,180,0,0.25)'
                      : 'none',
                  animation: isRunning ? 'pulse-glow 2s ease-in-out infinite' : isDone ? 'step-complete 0.4s cubic-bezier(0.16,1,0.3,1) both' : 'none',
                }}
              >
                {isDone ? (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <polyline
                      points="3.5,8.5 6.5,11.5 12.5,5"
                      stroke="var(--bg-base)"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : isRunning ? (
                  <div
                    className="w-2.5 h-2.5 rounded-full"
                    style={{
                      background: 'var(--status-running)',
                      animation: 'shimmer 0.8s ease-in-out infinite',
                    }}
                  />
                ) : (
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '11px',
                      fontWeight: 700,
                      color: 'var(--text-low)',
                      letterSpacing: '0.02em',
                    }}
                  >
                    {String(i + 1).padStart(2, '0')}
                  </span>
                )}
              </div>

              {/* Labels */}
              <div className="text-center">
                <div
                  className="text-[12px] font-semibold leading-tight mb-0.5"
                  style={{
                    fontFamily: 'var(--font-manrope)',
                    color: isDone
                      ? 'var(--accent-light)'
                      : isRunning
                        ? 'var(--status-running)'
                        : 'var(--text-mid)',
                  }}
                >
                  {meta.label}
                </div>
                <div
                  className="text-[9px] leading-snug hidden sm:block"
                  style={{
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--text-low)',
                    letterSpacing: '0.04em',
                  }}
                >
                  {meta.desc}
                </div>
              </div>

              {/* Phase code */}
              <div
                className="absolute top-2 right-2 text-[8px] font-bold"
                style={{
                  fontFamily: 'var(--font-mono)',
                  letterSpacing: '0.05em',
                  color: isDone ? 'var(--accent)' : 'var(--text-faint)',
                  opacity: 0.6,
                }}
              >
                {meta.code}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
