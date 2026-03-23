'use client'
import { useEffect, useReducer } from 'react'
import { createSSEConnection } from '@/lib/sse'
import { getRunStreamUrl } from '@/lib/api-client'
import { AGENT_STEPS } from '@/lib/types/run'
import type { AgentStep } from '@/lib/types/run'
import type { RunStreamState } from '../types'

const initialState: RunStreamState = {
  status: 'connecting',
  steps:   Object.fromEntries(AGENT_STEPS.map((s) => [s, 'pending'])) as RunStreamState['steps'],
  reports: Object.fromEntries(AGENT_STEPS.map((s) => [s, []])) as RunStreamState['reports'],
  verdict: null,
  error: null,
}

type Action =
  | { type: 'AGENT_START'; step: AgentStep; turn: number }
  | { type: 'AGENT_COMPLETE'; step: AgentStep; turn: number; report: string }
  | { type: 'RUN_COMPLETE'; decision: string }
  | { type: 'RUN_ERROR'; message: string }
  | { type: 'CONNECTED' }

function reducer(state: RunStreamState, action: Action): RunStreamState {
  switch (action.type) {
    case 'CONNECTED':
      return { ...state, status: 'running' }

    case 'AGENT_START':
      // Only transition to 'running' on first turn (don't regress from 'done')
      if (state.steps[action.step] !== 'pending') return state
      return { ...state, steps: { ...state.steps, [action.step]: 'running' } }

    case 'AGENT_COMPLETE':
      return {
        ...state,
        steps: { ...state.steps, [action.step]: 'done' },
        reports: {
          ...state.reports,
          [action.step]: [...(state.reports[action.step] ?? []), action.report],
        },
      }

    case 'RUN_COMPLETE':
      return { ...state, status: 'complete', verdict: action.decision as RunStreamState['verdict'] }

    case 'RUN_ERROR':
      return { ...state, status: 'error', error: action.message }

    default:
      return state
  }
}

export function useRunStream(runId: string): RunStreamState {
  const [state, dispatch] = useReducer(reducer, initialState)

  useEffect(() => {
    const url = getRunStreamUrl(runId)
    const close = createSSEConnection(url, {
      onOpen:          ()  => dispatch({ type: 'CONNECTED' }),
      onAgentStart:    ({ step, turn }) =>
        dispatch({ type: 'AGENT_START', step: step as AgentStep, turn }),
      onAgentComplete: ({ step, turn, report }) =>
        dispatch({ type: 'AGENT_COMPLETE', step: step as AgentStep, turn, report }),
      onRunComplete:   ({ decision }) => dispatch({ type: 'RUN_COMPLETE', decision }),
      onRunError:      ({ message })  => dispatch({ type: 'RUN_ERROR', message }),
    })
    return close
  }, [runId])

  return state
}
