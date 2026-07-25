import type { AnalysisEvent, AnalysisJob, AnalysisState } from './types'

export const initialAnalysisState: AnalysisState = {
  status: 'idle',
  lastEventId: 0,
  connected: false,
  agents: {},
  reports: {},
}

export type Action =
  | { type: 'created'; jobId: string }
  | { type: 'connected'; value: boolean }
  | { type: 'event'; event: AnalysisEvent }
  | { type: 'reset' }
  | { type: 'error'; message: string }
  | { type: 'cancelling' }
  | { type: 'loaded'; job: AnalysisJob }

export function analysisReducer(state: AnalysisState, action: Action): AnalysisState {
  if (action.type === 'reset') return initialAnalysisState
  if (action.type === 'created') return { ...initialAnalysisState, status: 'queued', jobId: action.jobId }
  if (action.type === 'connected') return { ...state, connected: action.value }
  if (action.type === 'error') return { ...state, status: 'failed', error: action.message }
  if (action.type === 'cancelling') return { ...state, status: 'cancelling' }
  if (action.type === 'loaded') {
    const result = action.job.result
    const reportKeys = ['market_report','sentiment_report','news_report','fundamentals_report','investment_plan','trader_investment_plan','final_trade_decision']
    const reports = Object.fromEntries(reportKeys.filter(key => typeof result?.[key] === 'string').map(key => [key, String(result?.[key])]))
    return { ...initialAnalysisState, status: action.job.status, jobId: action.job.job_id, result, reports, error: action.job.error?.message, providerRateLimit: action.job.error?.code === 'PROVIDER_RATE_LIMITED' ? action.job.error as import('./types').ProviderRateLimitError : undefined, providerTimeout: action.job.error?.code === 'PROVIDER_TIMED_OUT' ? action.job.error as import('./types').ProviderTimeoutError : undefined, reportId: action.job.report_id, adviceId: action.job.advice_id }
  }
  const event = action.event
  if (event.id <= state.lastEventId) return state
  const next = { ...state, lastEventId: event.id }
  const agent = String(event.data.agent ?? '')
  if (event.type === 'analysis.started') next.status = 'running'
  if (event.type === 'agent.started') next.agents = { ...state.agents, [agent]: 'running' }
  if (event.type === 'agent.completed') next.agents = { ...state.agents, [agent]: 'completed' }
  if (event.type === 'agent.skipped') next.agents = { ...state.agents, [agent]: 'skipped' }
  if (event.type === 'report.updated') {
    next.reports = { ...state.reports, [String(event.data.section)]: String(event.data.content ?? '') }
  }
  if (event.type === 'analysis.completed') {
    next.status = 'completed'
    next.result = event.data.result as AnalysisState['result']
    next.connected = false
    next.reportId = String(event.data.report_id ?? '') || undefined
    next.adviceId = String(event.data.advice_id ?? '') || undefined
  }
  if (event.type === 'analysis.failed') {
    next.status = 'failed'
    next.error = String(event.data.message ?? 'Analysis failed')
    next.connected = false
  }
  if (event.type === 'analysis.cancelled') {
    next.status = 'cancelled'
    next.connected = false
  }
  if (event.type === 'analysis.interrupted') {
    next.status = 'interrupted'
    next.connected = false
  }
  if (event.type === 'analysis.budget_exhausted') {
    next.status = 'budget_exhausted'
    next.result = event.data.result as AnalysisState['result']
    next.reportId = String(event.data.report_id ?? '') || undefined
    next.adviceId = String(event.data.advice_id ?? '') || undefined
    next.error = String((event.data.error as { message?: string } | undefined)?.message ?? 'Budget exhausted')
    next.connected = false
  }
  if (event.type === 'analysis.provider_rate_limited') {
    next.status = 'provider_rate_limited'
    next.error = String((event.data.error as { message?: string } | undefined)?.message ?? 'Yahoo Finance is temporarily rate limited')
    next.providerRateLimit = event.data.error as import('./types').ProviderRateLimitError
    next.connected = false
  }
  if (event.type === 'analysis.provider_timed_out') {
    next.status = 'provider_timed_out'
    next.error = String((event.data.error as { message?: string } | undefined)?.message ?? 'Yahoo Finance did not respond in time')
    next.providerTimeout = event.data.error as import('./types').ProviderTimeoutError
    next.connected = false
  }
  return next
}
