import { analysisReducer, initialAnalysisState } from './analysisReducer'
import type { AnalysisEvent } from './types'

function event(id: number, type: string, data: Record<string, unknown> = {}): AnalysisEvent {
  return { id, type, data, job_id: 'job', timestamp: '2026-07-22T00:00:00Z' }
}

describe('analysisReducer', () => {
  it('handles ordered lifecycle events and ignores duplicate ids', () => {
    let state = analysisReducer(initialAnalysisState, { type: 'created', jobId: 'job' })
    state = analysisReducer(state, { type: 'event', event: event(1, 'analysis.started') })
    state = analysisReducer(state, { type: 'event', event: event(2, 'agent.started', { agent: 'Market Analyst' }) })
    state = analysisReducer(state, { type: 'event', event: event(3, 'agent.completed', { agent: 'Market Analyst' }) })
    const duplicate = analysisReducer(state, { type: 'event', event: event(3, 'analysis.failed', { message: 'wrong' }) })
    expect(duplicate.status).toBe('running')
    expect(duplicate.agents['Market Analyst']).toBe('completed')
  })

  it('stores reports, final result, failure, and cancellation states', () => {
    let state = analysisReducer(initialAnalysisState, { type: 'event', event: event(1, 'report.updated', { section: 'fundamentals_report', content: 'Fund report' }) })
    expect(state.reports.fundamentals_report).toBe('Fund report')
    state = analysisReducer(state, { type: 'event', event: event(2, 'analysis.completed', { result: { asset_type: 'fund' } }) })
    expect(state.status).toBe('completed')
    expect(state.result?.asset_type).toBe('fund')
    expect(analysisReducer(state, { type: 'event', event: event(3, 'analysis.cancelled') }).status).toBe('cancelled')
  })

  it('stores a provider-rate-limited terminal state with safe cache detail', () => {
    const state = analysisReducer(initialAnalysisState, {
      type: 'event',
      event: event(1, 'analysis.provider_rate_limited', {
        error: {
          code: 'PROVIDER_RATE_LIMITED',
          message: 'Yahoo Finance is temporarily rate limited. Try again later.',
          provider: 'yahoo_finance',
          observed_at: '2026-07-24T00:00:00+00:00',
          cache_status: 'expired',
        },
      }),
    })
    expect(state.status).toBe('provider_rate_limited')
    expect(state.providerRateLimit?.cache_status).toBe('expired')
  })

  it('stores a provider timeout as a distinct retryable terminal state', () => {
    const state = analysisReducer(initialAnalysisState, {
      type: 'event',
      event: event(1, 'analysis.provider_timed_out', {
        error: {
          code: 'PROVIDER_TIMED_OUT',
          message: 'Yahoo Finance did not respond in time. Retry when you are ready.',
          provider: 'yahoo_finance',
          observed_at: '2026-07-24T00:00:00+00:00',
          cache_status: 'miss',
          timeout_seconds: 10,
        },
      }),
    })
    expect(state.status).toBe('provider_timed_out')
    expect(state.providerTimeout?.timeout_seconds).toBe(10)
  })
})
