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

jest.mock('@/lib/api-client', () => ({
  getRunStreamUrl: (id: string) => `/api/runs/${id}/stream`,
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
