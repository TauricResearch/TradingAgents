import type { AgentStep, RunStatus } from '@/lib/types/run'
import type { Decision, StepStatus } from '@/lib/types/agents'

export type RunStreamState = {
  status: RunStatus | 'connecting'
  steps: Record<AgentStep, StepStatus>
  reports: Record<AgentStep, string[]>
  verdict: Decision | null
  error: string | null
}
