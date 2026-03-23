import { renderHook, act } from '@testing-library/react'
import { useRunStream } from '@/features/run-detail/hooks/useRunStream'

jest.mock('@/lib/sse', () => ({
  createSSEConnection: jest.fn((url: string, handlers: Record<string, (d: unknown) => void>) => {
    setTimeout(() => {
      // First turn of bull_researcher
      handlers.onAgentStart?.({ step: 'bull_researcher', turn: 0 })
      handlers.onAgentComplete?.({ step: 'bull_researcher', turn: 0, report: 'Bull case round 1' })
      // Second turn of bull_researcher
      handlers.onAgentStart?.({ step: 'bull_researcher', turn: 1 })
      handlers.onAgentComplete?.({ step: 'bull_researcher', turn: 1, report: 'Bull case round 2' })
      handlers.onRunComplete?.({ decision: 'BUY', run_id: 'abc' })
    }, 0)
    return jest.fn()
  }),
}))

// getRun defaults to 'queued' so existing SSE-path tests still exercise the SSE branch.
// Tests that need a different status use mockResolvedValueOnce to override.
jest.mock('@/lib/api-client', () => ({
  getRunStreamUrl: (id: string) => `/api/runs/${id}/stream`,
  getRun: jest.fn().mockResolvedValue({
    id: 'abc',
    ticker: 'NVDA',
    date: '2026-03-23',
    status: 'queued',
    decision: null,
    created_at: '2026-03-23T00:00:00Z',
    config: null,
    reports: {},
    error: null,
  }),
}))

test('appends multiple turns for same step', async () => {
  const { result } = renderHook(() => useRunStream('abc'))
  await act(async () => { await new Promise((r) => setTimeout(r, 10)) })
  expect(result.current.reports['bull_researcher']).toEqual([
    'Bull case round 1',
    'Bull case round 2',
  ])
})

test('step status stays done after multiple turns', async () => {
  const { result } = renderHook(() => useRunStream('abc'))
  await act(async () => { await new Promise((r) => setTimeout(r, 10)) })
  expect(result.current.steps['bull_researcher']).toBe('done')
})

test('verdict and status set on run:complete', async () => {
  const { result } = renderHook(() => useRunStream('abc'))
  await act(async () => { await new Promise((r) => setTimeout(r, 10)) })
  expect(result.current.verdict).toBe('BUY')
  expect(result.current.status).toBe('complete')
})

test('initial reports are empty arrays', () => {
  const { result } = renderHook(() => useRunStream('abc'))
  expect(result.current.reports['market_analyst']).toEqual([])
})

test('hydrates from reports when run is complete, skipping SSE', async () => {
  const { getRun } = jest.requireMock('@/lib/api-client')
  const { createSSEConnection } = jest.requireMock('@/lib/sse')

  // Reset call history so we can assert createSSEConnection was NOT called for this run
  jest.clearAllMocks()

  getRun.mockResolvedValueOnce({
    id: 'xyz',
    ticker: 'AAPL',
    date: '2026-03-23',
    status: 'complete',
    decision: 'SELL',
    created_at: '2026-03-23T00:00:00Z',
    config: null,
    reports: { 'market_analyst:0': 'bearish signal' },
    error: null,
  })

  const { result } = renderHook(() => useRunStream('xyz'))
  await act(async () => { await new Promise((r) => setTimeout(r, 10)) })

  expect(result.current.status).toBe('complete')
  expect(result.current.verdict).toBe('SELL')
  expect(result.current.reports['market_analyst']).toEqual(['bearish signal'])
  expect(createSSEConnection).not.toHaveBeenCalled()  // SSE skipped for completed run
})

test('AGENT_COMPLETE accumulates tokensByStep and tokensTotal', async () => {
  const { getRun } = jest.requireMock('@/lib/api-client')
  const { createSSEConnection } = jest.requireMock('@/lib/sse')
  jest.clearAllMocks()

  // getRun returns queued so SSE path runs
  getRun.mockResolvedValueOnce({
    id: 'abc', ticker: 'NVDA', date: '2026-03-23', status: 'queued',
    decision: null, created_at: '2026-03-23T00:00:00Z',
    config: null, reports: {}, error: null, token_usage: null,
  })

  // SSE mock emits one agent:complete with token data
  createSSEConnection.mockImplementationOnce(
    (_url: string, handlers: Record<string, (d: unknown) => void>) => {
      setTimeout(() => {
        handlers.onAgentStart?.({ step: 'market_analyst', turn: 0 })
        handlers.onAgentComplete?.({
          step: 'market_analyst', turn: 0, report: 'bullish',
          tokens_in: 1200, tokens_out: 400,
        })
        handlers.onRunComplete?.({ decision: 'BUY', run_id: 'abc' })
      }, 0)
      return jest.fn()
    }
  )

  const { result } = renderHook(() => useRunStream('abc'))
  await act(async () => { await new Promise((r) => setTimeout(r, 10)) })

  expect(result.current.tokensByStep['market_analyst']).toEqual({ in: 1200, out: 400 })
  expect(result.current.tokensTotal).toEqual({ in: 1200, out: 400 })
})

test('missing tokens_in/out in AGENT_COMPLETE defaults to 0', async () => {
  const { getRun } = jest.requireMock('@/lib/api-client')
  const { createSSEConnection } = jest.requireMock('@/lib/sse')
  jest.clearAllMocks()

  getRun.mockResolvedValueOnce({
    id: 'abc', ticker: 'NVDA', date: '2026-03-23', status: 'queued',
    decision: null, created_at: '2026-03-23T00:00:00Z',
    config: null, reports: {}, error: null, token_usage: null,
  })

  createSSEConnection.mockImplementationOnce(
    (_url: string, handlers: Record<string, (d: unknown) => void>) => {
      setTimeout(() => {
        handlers.onAgentStart?.({ step: 'news_analyst', turn: 0 })
        // No tokens_in/tokens_out in payload
        handlers.onAgentComplete?.({ step: 'news_analyst', turn: 0, report: 'ok' })
        handlers.onRunComplete?.({ decision: 'HOLD', run_id: 'abc' })
      }, 0)
      return jest.fn()
    }
  )

  const { result } = renderHook(() => useRunStream('abc'))
  await act(async () => { await new Promise((r) => setTimeout(r, 10)) })

  expect(result.current.tokensByStep['news_analyst']).toEqual({ in: 0, out: 0 })
  expect(result.current.tokensTotal).toEqual({ in: 0, out: 0 })
})

test('completed-run hydration populates tokens from getRun().token_usage without SSE', async () => {
  const { getRun } = jest.requireMock('@/lib/api-client')
  const { createSSEConnection } = jest.requireMock('@/lib/sse')
  jest.clearAllMocks()

  getRun.mockResolvedValueOnce({
    id: 'tok', ticker: 'AAPL', date: '2026-03-23', status: 'complete',
    decision: 'BUY', created_at: '2026-03-23T00:00:00Z',
    config: null,
    reports: { 'market_analyst:0': 'bullish' },
    error: null,
    token_usage: { 'market_analyst:0': { tokens_in: 1200, tokens_out: 400 } },
  })

  const { result } = renderHook(() => useRunStream('tok'))
  await act(async () => { await new Promise((r) => setTimeout(r, 10)) })

  expect(createSSEConnection).not.toHaveBeenCalled()
  expect(result.current.status).toBe('complete')
  expect(result.current.tokensByStep['market_analyst']).toEqual({ in: 1200, out: 400 })
  expect(result.current.tokensTotal).toEqual({ in: 1200, out: 400 })
})
