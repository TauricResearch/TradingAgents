import { AGENT_STEPS, STEP_PHASE } from '@/lib/types/run'
import type { AgentStep } from '@/lib/types/run'
import type { StepStatus } from '@/lib/types/agents'

type Phase = 'analysts' | 'researchers' | 'trader' | 'risk'
type Props = { steps: Record<string, StepStatus> }

const PHASES: Phase[] = ['analysts', 'researchers', 'trader', 'risk']
const PHASE_LABELS: Record<Phase, string> = {
  analysts: 'Analysts', researchers: 'Researchers', trader: 'Trader', risk: 'Risk',
}
const PHASE_NUMS: Record<Phase, string> = {
  analysts: '01', researchers: '02', trader: '03', risk: '04',
}

function phaseStatus(phase: Phase, steps: Record<string, StepStatus>): StepStatus {
  const phaseSteps = AGENT_STEPS.filter((s) => STEP_PHASE[s as AgentStep] === phase)
  if (phaseSteps.every((s) => steps[s] === 'done')) return 'done'
  if (phaseSteps.some((s) => steps[s] === 'running')) return 'running'
  return 'pending'
}

export default function PipelineStepper({ steps }: Props) {
  return (
    <div
      className="px-6 py-5"
      style={{
        background:   'var(--bg-card)',
        border:       '1px solid var(--border)',
        borderRadius: '10px',
      }}
    >
      <div
        className="apex-label mb-4"
      >
        Pipeline
      </div>
      <div className="flex items-center gap-0">
        {PHASES.map((phase, i) => {
          const status    = phaseStatus(phase, steps)
          const isDone    = status === 'done'
          const isRunning = status === 'running'
          const isPending = status === 'pending'

          return (
            <div key={phase} className="flex items-center flex-1 last:flex-none">
              {/* Step node */}
              <div className="flex flex-col items-center gap-2 relative">
                {/* Circle */}
                <div
                  className="relative w-9 h-9 rounded-full flex items-center justify-center transition-all duration-500"
                  style={{
                    background: isDone
                      ? 'var(--accent)'
                      : isRunning
                        ? 'var(--bg-elevated)'
                        : 'var(--bg-elevated)',
                    border: isDone
                      ? '2px solid var(--accent)'
                      : isRunning
                        ? '2px solid var(--status-running)'
                        : '1px solid var(--status-pending)',
                    boxShadow: isDone
                      ? '0 0 16px var(--accent-glow)'
                      : isRunning
                        ? '0 0 12px rgba(245,158,11,0.20)'
                        : 'none',
                    animation: isRunning ? 'pulse-glow 2s ease-in-out infinite' : 'none',
                  }}
                >
                  {isDone ? (
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <polyline
                        points="3,7 5.5,9.5 11,4"
                        stroke="white"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  ) : isRunning ? (
                    <div
                      className="w-2 h-2 rounded-full"
                      style={{
                        background: 'var(--status-running)',
                        animation:  'shimmer 1s ease-in-out infinite',
                      }}
                    />
                  ) : (
                    <span
                      className="text-[10px] font-bold"
                      style={{ color: 'var(--text-low)', fontFamily: 'var(--font-manrope)' }}
                    >
                      {PHASE_NUMS[phase]}
                    </span>
                  )}
                </div>

                {/* Label */}
                <span
                  className="text-[10px] font-medium text-center whitespace-nowrap transition-all duration-300"
                  style={{
                    color:      isDone ? 'var(--accent-light)' : isRunning ? 'var(--status-running)' : 'var(--text-low)',
                    fontFamily: 'var(--font-manrope)',
                    letterSpacing: '0.04em',
                  }}
                >
                  {PHASE_LABELS[phase]}
                </span>
              </div>

              {/* Connector */}
              {i < PHASES.length - 1 && (
                <div
                  className="flex-1 h-px mx-3 transition-all duration-700 relative overflow-hidden"
                  style={{
                    background: isDone ? 'var(--accent)' : 'var(--border)',
                    boxShadow:  isDone ? '0 0 6px var(--accent-glow)' : 'none',
                    marginBottom: '20px',
                  }}
                >
                  {isRunning && (
                    <div
                      className="absolute inset-y-0 w-1/2 bg-gradient-to-r from-transparent via-yellow-400 to-transparent opacity-60"
                      style={{ animation: 'scan-line 1.5s ease-in-out infinite' }}
                    />
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
