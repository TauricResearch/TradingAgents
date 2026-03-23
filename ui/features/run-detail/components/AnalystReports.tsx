import { AGENT_STEPS, AGENT_STEP_LABELS, STEP_PHASE } from '@/lib/types/run'
import type { AgentStep } from '@/lib/types/run'
import type { StepStatus } from '@/lib/types/agents'

type Phase = 'analysts' | 'researchers' | 'trader' | 'risk'

const MULTI_TURN_STEPS = new Set<AgentStep>([
  'bull_researcher', 'bear_researcher',
  'aggressive_analyst', 'conservative_analyst', 'neutral_analyst',
])

const STEP_ACCENT: Record<AgentStep, string> = {
  market_analyst:       '#00C4E8',
  news_analyst:         '#A78BFA',
  fundamentals_analyst: '#00E078',
  social_analyst:       '#FFB400',
  bull_researcher:      '#00E078',
  bear_researcher:      '#FF1F4C',
  research_manager:     '#00C4E8',
  trader:               '#FFB400',
  aggressive_analyst:   '#FF1F4C',
  conservative_analyst: '#00C4E8',
  neutral_analyst:      '#A78BFA',
  risk_judge:           '#FFB400',
}

const STEP_ROLE_DESC: Partial<Record<AgentStep, string>> = {
  market_analyst:       'Technical & price action',
  news_analyst:         'Sentiment & headlines',
  fundamentals_analyst: 'Earnings & financials',
  social_analyst:       'Social signals',
  bull_researcher:      'Bullish thesis',
  bear_researcher:      'Bearish thesis',
  research_manager:     'Research synthesis',
  trader:               'Trade plan',
  aggressive_analyst:   'High-risk perspective',
  conservative_analyst: 'Risk-averse perspective',
  neutral_analyst:      'Balanced view',
  risk_judge:           'Final risk decision',
}

type Props = {
  phase: Phase
  steps: Record<AgentStep, StepStatus>
  reports: Record<AgentStep, string[]>
}

export default function AnalystReports({ phase, steps, reports }: Props) {
  const phaseSteps = AGENT_STEPS.filter((s) => STEP_PHASE[s] === phase)

  return (
    <div className="space-y-3">
      {phaseSteps.map((step, stepIdx) => {
        const stepStatus = steps[step] ?? 'pending'
        const turns      = reports[step] ?? []
        const isRunning  = stepStatus === 'running'
        const isDone     = stepStatus === 'done'
        const isMulti    = MULTI_TURN_STEPS.has(step)
        const accent     = STEP_ACCENT[step]
        const roleDesc   = STEP_ROLE_DESC[step]

        return (
          <div key={step} className="animate-fade-up" style={{ animationDelay: `${stepIdx * 40}ms` }}>
            {/* Completed turns */}
            {turns.map((report, i) => (
              <div
                key={`${step}-${i}`}
                className="mb-2.5 overflow-hidden"
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-raised)',
                  borderRadius: '12px',
                }}
              >
                {/* Colored header bar */}
                <div
                  className="px-4 py-2.5 flex items-center justify-between"
                  style={{
                    background: `${accent}0D`,
                    borderBottom: `1px solid ${accent}20`,
                  }}
                >
                  <div className="flex items-center gap-2.5">
                    <div
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ background: accent, boxShadow: `0 0 6px ${accent}80` }}
                    />
                    <span
                      className="text-[13px] font-semibold"
                      style={{ color: 'var(--text-high)', fontFamily: 'var(--font-manrope)' }}
                    >
                      {AGENT_STEP_LABELS[step]}
                    </span>
                    {roleDesc && (
                      <span
                        className="text-[10px]"
                        style={{ color: accent, opacity: 0.7, fontFamily: 'var(--font-mono)', letterSpacing: '0.04em' }}
                      >
                        · {roleDesc}
                      </span>
                    )}
                    {isMulti && (
                      <span
                        className="px-2 py-0.5 rounded text-[9px] font-bold"
                        style={{
                          background: `${accent}18`,
                          color: accent,
                          fontFamily: 'var(--font-mono)',
                          letterSpacing: '0.06em',
                        }}
                      >
                        T{i + 1}
                      </span>
                    )}
                  </div>

                  <div
                    className="flex items-center gap-1.5 text-[10px] font-bold"
                    style={{
                      fontFamily: 'var(--font-mono)',
                      letterSpacing: '0.08em',
                      color: 'var(--buy)',
                    }}
                  >
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                      <polyline points="2,5 4,7 8,3" stroke="var(--buy)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                    DONE
                  </div>
                </div>

                {/* Report body */}
                <div className="px-4 py-3">
                  <p
                    className="text-sm leading-relaxed line-clamp-5"
                    style={{ color: 'var(--text-mid)', lineHeight: '1.75', fontFamily: 'var(--font-manrope)' }}
                  >
                    {report}
                  </p>
                </div>
              </div>
            ))}

            {/* Running state */}
            {isRunning && (
              <div
                className="mb-2.5 overflow-hidden"
                style={{
                  background: 'var(--bg-elevated)',
                  border: '1px solid rgba(255,180,0,0.20)',
                  borderRadius: '12px',
                }}
              >
                <div
                  className="px-4 py-2.5 flex items-center justify-between"
                  style={{
                    background: 'rgba(255,180,0,0.06)',
                    borderBottom: '1px solid rgba(255,180,0,0.12)',
                  }}
                >
                  <div className="flex items-center gap-2.5">
                    <div
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ background: accent, animation: 'shimmer 0.8s infinite' }}
                    />
                    <span
                      className="text-[13px] font-semibold"
                      style={{ color: 'var(--text-high)', fontFamily: 'var(--font-manrope)' }}
                    >
                      {AGENT_STEP_LABELS[step]}
                    </span>
                    {isMulti && turns.length > 0 && (
                      <span
                        className="px-2 py-0.5 rounded text-[9px] font-bold"
                        style={{
                          background: `${accent}18`,
                          color: accent,
                          fontFamily: 'var(--font-mono)',
                          letterSpacing: '0.06em',
                        }}
                      >
                        T{turns.length + 1}
                      </span>
                    )}
                  </div>

                  <div
                    className="flex items-center gap-1.5 text-[10px] font-bold"
                    style={{ fontFamily: 'var(--font-mono)', letterSpacing: '0.08em', color: 'var(--status-running)' }}
                  >
                    <div
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ background: 'var(--status-running)', animation: 'shimmer 0.7s infinite' }}
                    />
                    ANALYZING
                  </div>
                </div>

                <div className="px-4 py-3 space-y-2">
                  {[85, 62, 44, 30].map((w, i) => (
                    <div
                      key={i}
                      className="h-2 rounded animate-shimmer"
                      style={{
                        background: 'var(--border-raised)',
                        width: `${w}%`,
                        animationDelay: `${i * 0.18}s`,
                      }}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Pending state */}
            {turns.length === 0 && !isRunning && (
              <div
                className="mb-2.5 overflow-hidden"
                style={{
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border)',
                  borderRadius: '12px',
                  opacity: 0.45,
                }}
              >
                <div className="px-4 py-2.5 flex items-center justify-between" style={{ borderBottom: '1px solid var(--border)' }}>
                  <div className="flex items-center gap-2.5">
                    <div className="w-2 h-2 rounded-full shrink-0" style={{ background: 'var(--text-low)' }} />
                    <span className="text-[13px] font-medium" style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-manrope)' }}>
                      {AGENT_STEP_LABELS[step]}
                    </span>
                  </div>
                  <span
                    className="text-[9px] font-bold"
                    style={{ fontFamily: 'var(--font-mono)', letterSpacing: '0.1em', color: 'var(--text-low)' }}
                  >
                    QUEUED
                  </span>
                </div>
                <div className="px-4 py-3">
                  <div className="h-2 rounded" style={{ background: 'var(--border)', width: '45%' }} />
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
