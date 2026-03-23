import { AGENT_STEPS, AGENT_STEP_LABELS, STEP_PHASE } from '@/lib/types/run'
import type { AgentStep } from '@/lib/types/run'
import type { StepStatus } from '@/lib/types/agents'

type Phase = 'analysts' | 'researchers' | 'trader' | 'risk'

const MULTI_TURN_STEPS = new Set<AgentStep>([
  'bull_researcher', 'bear_researcher',
  'aggressive_analyst', 'conservative_analyst', 'neutral_analyst',
])

// Color accent per step for visual differentiation
const STEP_ACCENT: Record<AgentStep, string> = {
  market_analyst:       '#4480FF',
  news_analyst:         '#A78BFA',
  fundamentals_analyst: '#00CE68',
  social_analyst:       '#F59E0B',
  bull_researcher:      '#00CE68',
  bear_researcher:      '#FF3355',
  research_manager:     '#4480FF',
  trader:               '#F59E0B',
  aggressive_analyst:   '#FF3355',
  conservative_analyst: '#4480FF',
  neutral_analyst:      '#A78BFA',
  risk_judge:           '#F59E0B',
}

type Props = {
  phase: Phase
  steps: Record<AgentStep, StepStatus>
  reports: Record<AgentStep, string[]>
}

export default function AnalystReports({ phase, steps, reports }: Props) {
  const phaseSteps = AGENT_STEPS.filter((s) => STEP_PHASE[s] === phase)

  return (
    <div className="space-y-2.5">
      {phaseSteps.map((step) => {
        const stepStatus = steps[step] ?? 'pending'
        const turns      = reports[step] ?? []
        const isRunning  = stepStatus === 'running'
        const isDone     = stepStatus === 'done'
        const isMulti    = MULTI_TURN_STEPS.has(step)
        const accent     = STEP_ACCENT[step]

        return (
          <div key={step}>
            {/* ── Completed turns ─────────────────────────────── */}
            {turns.map((report, i) => (
              <div
                key={`${step}-${i}`}
                className="p-5 mb-2"
                style={{
                  background:   'var(--bg-card)',
                  border:       '1px solid var(--border-raised)',
                  borderLeft:   `3px solid ${accent}`,
                  borderRadius: '10px',
                }}
              >
                {/* Header */}
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-2 h-2 rounded-full"
                      style={{ background: accent, flexShrink: 0 }}
                    />
                    <span
                      className="text-[13px] font-semibold"
                      style={{ color: 'var(--text-high)', fontFamily: 'var(--font-manrope)' }}
                    >
                      {AGENT_STEP_LABELS[step]}
                    </span>
                    {isMulti && (
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                        style={{
                          background:  `${accent}18`,
                          color:       accent,
                          fontFamily:  'var(--font-manrope)',
                        }}
                      >
                        Turn {i + 1}
                      </span>
                    )}
                  </div>
                  <div
                    className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium"
                    style={{
                      background: 'rgba(0,206,104,0.08)',
                      color:      '#00CE68',
                      border:     '1px solid rgba(0,206,104,0.20)',
                    }}
                  >
                    <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#00CE68' }} />
                    Done
                  </div>
                </div>

                {/* Report text */}
                <p
                  className="text-sm leading-relaxed line-clamp-5"
                  style={{ color: 'var(--text-mid)', lineHeight: '1.7' }}
                >
                  {report}
                </p>
              </div>
            ))}

            {/* ── Running spinner ──────────────────────────────── */}
            {isRunning && (
              <div
                className="p-5 mb-2"
                style={{
                  background:   'var(--bg-elevated)',
                  border:       '1px solid var(--border)',
                  borderLeft:   `3px solid var(--status-running)`,
                  borderRadius: '10px',
                  opacity: 0.9,
                }}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-2 h-2 rounded-full"
                      style={{
                        background: accent,
                        animation:  'shimmer 1s ease-in-out infinite',
                        flexShrink: 0,
                      }}
                    />
                    <span
                      className="text-[13px] font-semibold"
                      style={{ color: 'var(--text-high)', fontFamily: 'var(--font-manrope)' }}
                    >
                      {AGENT_STEP_LABELS[step]}
                    </span>
                    {isMulti && turns.length > 0 && (
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                        style={{
                          background:  `${accent}18`,
                          color:       accent,
                          fontFamily:  'var(--font-manrope)',
                        }}
                      >
                        Turn {turns.length + 1}
                      </span>
                    )}
                  </div>
                  <div
                    className="flex items-center gap-1.5 text-[10px] font-medium"
                    style={{ color: 'var(--status-running)', fontFamily: 'var(--font-manrope)' }}
                  >
                    <div
                      className="w-1.5 h-1.5 rounded-full"
                      style={{
                        background: 'var(--status-running)',
                        animation:  'shimmer 1s ease-in-out infinite',
                      }}
                    />
                    Analyzing
                  </div>
                </div>

                {/* Shimmer lines */}
                <div className="space-y-2">
                  <div
                    className="h-2.5 rounded animate-shimmer"
                    style={{ background: 'var(--border-raised)', width: '85%' }}
                  />
                  <div
                    className="h-2.5 rounded animate-shimmer"
                    style={{ background: 'var(--border-raised)', width: '65%', animationDelay: '0.2s' }}
                  />
                  <div
                    className="h-2.5 rounded animate-shimmer"
                    style={{ background: 'var(--border-raised)', width: '45%', animationDelay: '0.4s' }}
                  />
                </div>
              </div>
            )}

            {/* ── Pending placeholder ──────────────────────────── */}
            {turns.length === 0 && !isRunning && (
              <div
                className="p-5 mb-2"
                style={{
                  background:   'var(--bg-elevated)',
                  border:       '1px solid var(--border)',
                  borderLeft:   `3px solid var(--border)`,
                  borderRadius: '10px',
                  opacity:      0.5,
                }}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-2 h-2 rounded-full"
                      style={{ background: 'var(--text-low)', flexShrink: 0 }}
                    />
                    <span
                      className="text-[13px] font-medium"
                      style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-manrope)' }}
                    >
                      {AGENT_STEP_LABELS[step]}
                    </span>
                  </div>
                  <span
                    className="text-[10px]"
                    style={{ color: 'var(--text-low)', fontFamily: 'var(--font-manrope)' }}
                  >
                    Queued
                  </span>
                </div>
                <div
                  className="h-2 rounded"
                  style={{ background: 'var(--border)', width: '40%' }}
                />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
