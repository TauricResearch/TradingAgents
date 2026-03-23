import type { AgentStep } from './run'

export type Decision = 'BUY' | 'SELL' | 'HOLD'
export type DebateTurn = { speaker: string; text: string }
export type PhaseReport = { step: AgentStep; content: string }
export type StepStatus = 'pending' | 'running' | 'done'
