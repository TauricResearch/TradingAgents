import type { AgentStep, RunStatus } from '@/lib/types/run'
import type { Decision, StepStatus } from '@/lib/types/agents'

export type TokenCount = { in: number; out: number }

export type RunStreamState = {
  status: RunStatus | 'connecting'
  steps: Record<AgentStep, StepStatus>
  reports: Record<AgentStep, string[]>
  verdict: Decision | null
  error: string | null
  tokensByStep: Record<AgentStep, TokenCount>
  tokensTotal: TokenCount
}
