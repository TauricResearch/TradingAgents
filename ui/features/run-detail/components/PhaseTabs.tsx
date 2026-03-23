'use client'
import { useState } from 'react'
import { AGENT_STEPS, STEP_PHASE } from '@/lib/types/run'
import type { AgentStep } from '@/lib/types/run'
import type { StepStatus } from '@/lib/types/agents'
import AnalystReports from './AnalystReports'

type Phase = 'analysts' | 'researchers' | 'trader' | 'risk'

const TABS: { label: string; phase: Phase; desc: string }[] = [
  { label: 'Analysts',    phase: 'analysts',    desc: '4 agents'   },
  { label: 'Researchers', phase: 'researchers', desc: '3 agents'   },
  { label: 'Trader',      phase: 'trader',      desc: '1 agent'    },
  { label: 'Risk',        phase: 'risk',        desc: '4 agents'   },
]

type Props = {
  steps:   Record<AgentStep, StepStatus>
  reports: Record<AgentStep, string[]>
}

function getPhaseCompletion(phase: Phase, steps: Record<AgentStep, StepStatus>): number {
  const phaseSteps = AGENT_STEPS.filter((s) => STEP_PHASE[s] === phase)
  const done = phaseSteps.filter((s) => steps[s as AgentStep] === 'done').length
  return phaseSteps.length > 0 ? Math.round((done / phaseSteps.length) * 100) : 0
}

export default function PhaseTabs({ steps, reports }: Props) {
  const [active, setActive] = useState<Phase>('analysts')

  return (
    <div>
      {/* Section label */}
      <div
        className="apex-label mb-3"
      >
        Agent Reports
      </div>

      {/* Tab bar */}
      <div
        className="flex gap-1 p-1 mb-5"
        style={{
          background:   'var(--bg-card)',
          border:       '1px solid var(--border)',
          borderRadius: '10px',
          width:        'fit-content',
        }}
      >
        {TABS.map(({ label, phase }) => {
          const isActive     = active === phase
          const completion   = getPhaseCompletion(phase, steps)
          const allDone      = completion === 100

          return (
            <button
              key={phase}
              onClick={() => setActive(phase)}
              className="relative flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-[13px] font-medium transition-all duration-150"
              style={
                isActive
                  ? {
                      background:  'var(--accent-glow)',
                      color:       'var(--accent-light)',
                      border:      '1px solid var(--border-active)',
                      fontFamily:  'var(--font-manrope)',
                    }
                  : {
                      color:      'var(--text-mid)',
                      fontFamily: 'var(--font-manrope)',
                    }
              }
            >
              {/* Done indicator dot */}
              {allDone && (
                <div
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ background: 'var(--buy)', flexShrink: 0 }}
                />
              )}
              {label}
            </button>
          )
        })}
      </div>

      {/* Reports */}
      <AnalystReports phase={active} steps={steps} reports={reports} />
    </div>
  )
}
