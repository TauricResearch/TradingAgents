'use client'
import { useEffect, useReducer } from 'react'
import { createSSEConnection } from '@/lib/sse'
import { getRun, getRunStreamUrl } from '@/lib/api-client'
import { AGENT_STEPS } from '@/lib/types/run'
import type { AgentStep } from '@/lib/types/run'
import type { RunStreamState, TokenCount } from '../types'

const zeroTokens = (): TokenCount => ({ in: 0, out: 0 })

const initialState: RunStreamState = {
  status: 'connecting',
  steps:        Object.fromEntries(AGENT_STEPS.map((s) => [s, 'pending'])) as RunStreamState['steps'],
  reports:      Object.fromEntries(AGENT_STEPS.map((s) => [s, []])) as RunStreamState['reports'],
  tokensByStep: Object.fromEntries(AGENT_STEPS.map((s) => [s, zeroTokens()])) as RunStreamState['tokensByStep'],
  tokensTotal:  zeroTokens(),
  verdict: null,
  error: null,
}

type Action =
  | { type: 'AGENT_START';    step: AgentStep; turn: number }
  | { type: 'AGENT_COMPLETE'; step: AgentStep; turn: number; report: string; tokens_in?: number; tokens_out?: number }
  | { type: 'RUN_COMPLETE';   decision: string }
  | { type: 'RUN_ERROR';      message: string }
  | { type: 'CONNECTED' }

function reducer(state: RunStreamState, action: Action): RunStreamState {
  switch (action.type) {
    case 'CONNECTED':
      return { ...state, status: 'running' }

    case 'AGENT_START':
      if (state.steps[action.step] !== 'pending') return state
      return { ...state, steps: { ...state.steps, [action.step]: 'running' } }

    case 'AGENT_COMPLETE': {
      const dIn  = action.tokens_in  ?? 0
      const dOut = action.tokens_out ?? 0
      const prev = state.tokensByStep[action.step] ?? zeroTokens()
      return {
        ...state,
        steps:   { ...state.steps,   [action.step]: 'done' },
        reports: {
          ...state.reports,
          [action.step]: [...(state.reports[action.step] ?? []), action.report],
        },
        tokensByStep: {
          ...state.tokensByStep,
          [action.step]: { in: prev.in + dIn, out: prev.out + dOut },
        },
        tokensTotal: {
          in:  state.tokensTotal.in  + dIn,
          out: state.tokensTotal.out + dOut,
        },
      }
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
    let close: (() => void) | undefined
    let aborted = false

    getRun(runId).then((run) => {
      if (aborted) return

      if (run.status === 'complete' && run.reports) {
        dispatch({ type: 'CONNECTED' })
        for (const [key, report] of Object.entries(run.reports)) {
          const lastColon = key.lastIndexOf(':')
          const step  = key.slice(0, lastColon) as AgentStep
          const turn  = parseInt(key.slice(lastColon + 1), 10)
          const tok   = run.token_usage?.[key] ?? { tokens_in: 0, tokens_out: 0 }
          dispatch({ type: 'AGENT_START',    step, turn })
          dispatch({ type: 'AGENT_COMPLETE', step, turn, report,
                     tokens_in: tok.tokens_in, tokens_out: tok.tokens_out })
        }
        dispatch({ type: 'RUN_COMPLETE', decision: run.decision ?? 'HOLD' })
        return
      }

      const url = getRunStreamUrl(runId)
      close = createSSEConnection(url, {
        onOpen:          () => dispatch({ type: 'CONNECTED' }),
        onAgentStart:    ({ step, turn }) =>
          dispatch({ type: 'AGENT_START', step: step as AgentStep, turn }),
        onAgentComplete: ({ step, turn, report, tokens_in, tokens_out }) =>
          dispatch({ type: 'AGENT_COMPLETE', step: step as AgentStep, turn, report,
                     tokens_in, tokens_out }),
        onRunComplete:   ({ decision }) => dispatch({ type: 'RUN_COMPLETE', decision }),
        onRunError:      ({ message })  => dispatch({ type: 'RUN_ERROR',    message }),
      })
    }).catch(() => {
      if (!aborted) dispatch({ type: 'RUN_ERROR', message: 'Failed to load run' })
    })

    return () => { aborted = true; close?.() }
  }, [runId])

  return state
}
