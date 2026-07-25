import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from './App'
import i18n, { UI_LANGUAGE_KEY } from './i18n'

class FakeEventSource {
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  addEventListener() {}
  close() {}
}

beforeEach(() => {
  window.localStorage.setItem(UI_LANGUAGE_KEY, 'en')
  void i18n.changeLanguage('en')
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/config/options')) return new Response(JSON.stringify({ budget: { limits: { max_requests_per_analysis: 10, max_total_tokens_per_analysis: 1000 }, historical_estimate: null, monetary_estimate: 'unknown', daily_usage: { requests: 0, tokens: 0 } } }), { status: 200 })
    if (url.includes('/resolve')) return new Response(JSON.stringify({ requested_symbol:'SPY', canonical_symbol:'SPY', asset_type:'fund', fund_type:'etf', quote_type:'ETF', name:'SPDR S&P 500 ETF Trust', exchange:'PCX', currency:'USD', warnings:[] }), { status: 200 })
    if (url.endsWith('/api/analyses') && !init?.method) return new Response(JSON.stringify({ items: [] }), { status: 200 })
    if (url.includes('/admin/backups')) return new Response(JSON.stringify({ items: [] }), { status: 200 })
    return new Response(JSON.stringify({ job_id:'job-1', status:'queued' }), { status: 202 })
  }))
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

it('submits a durable job without requiring a browser-side provider probe and renders identity when resolved', async () => {
  render(<App />)
  expect(screen.getByRole('button', { name: /start analysis/i })).toBeEnabled()
  fireEvent.click(screen.getByRole('button', { name: 'Resolve' }))
  await waitFor(() => expect(screen.getAllByText('SPDR S&P 500 ETF Trust')).toHaveLength(2))
  expect(screen.getByRole('button', { name: /start analysis/i })).toBeEnabled()
})

it('renders stable empty report states and accessible export action', () => {
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Analyst Reports' }))
  expect(screen.getByText('No report content yet')).toBeInTheDocument()
  expect(screen.getByLabelText('Download Markdown report')).toBeInTheDocument()
})

it('exposes persistence, trust, usage, advice, chat, and recovery views', async () => {
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'History' }))
  expect(await screen.findByText('Analysis history')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Data Quality' }))
  expect(screen.getByText('No data quality assessment')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Usage' }))
  expect(screen.getByText('Configured budget')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Advice' }))
  expect(screen.getByText('No formal advice')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Q&A' }))
  expect(screen.getByText('Report Q&A unavailable')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Backup' }))
  expect(await screen.findByText('Backup and restore')).toBeInTheDocument()
})

it('switches and persists interface language without changing report language', async () => {
  render(<App />)
  fireEvent.change(screen.getByLabelText('Interface language'), { target: { value: 'zh' } })
  expect(await screen.findByRole('button', { name: '开始分析' })).toBeInTheDocument()
  expect(window.localStorage.getItem(UI_LANGUAGE_KEY)).toBe('zh')
  expect(screen.getByLabelText('报告语言')).toHaveValue('English')
})

it('submits the independently selected report language', async () => {
  render(<App />)
  fireEvent.change(screen.getByLabelText('Report language'), { target: { value: 'Chinese' } })
  fireEvent.click(screen.getByRole('button', { name: 'Start analysis' }))
  await waitFor(() => {
    const calls = vi.mocked(fetch).mock.calls
    const request = calls.find(([url, init]) => String(url).endsWith('/api/analyses') && init?.method === 'POST')
    expect(request).toBeDefined()
    expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({ output_language: 'Chinese' })
  })
})
