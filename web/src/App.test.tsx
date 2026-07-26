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
    if (url.includes('/api/funds/search')) return new Response(JSON.stringify({ items: [{ code:'016453', display_name:'南方纳斯达克100指数(QDII)C', share_class:'C', vehicle_type:'index_feeder', strategy_type:'index', market_scope:'qdii', tags:['US / QDII'] }] }), { status: 200 })
    if (url.includes('/api/funds/016453/snapshot')) return new Response(JSON.stringify({
      identity: { code:'016453', display_name:'南方纳斯达克100指数(QDII)C', share_class:'C', vehicle_type:'index_feeder', strategy_type:'index', market_scope:'qdii', currency:'CNY', tags:['US / QDII'], warnings:[] },
      analysis_date:'2026-07-25', retrieved_at:'2026-07-25T08:00:00+00:00',
      nav_history:[{date:'2026-07-23', nav:'1.0100'},{date:'2026-07-24', nav:'1.0200'}],
      transaction_status:{subscription:'开放申购', redemption:'开放赎回', observed_at:'2026-07-25T08:00:00+00:00'},
      fees:[], metrics:[{name:'total_return',value:0.01,unit:'percent'}], evidence:[{name:'nav_history',value:'available',source_reference:'fixture://fund/nav',retrieved_at:'2026-07-25T08:00:00+00:00',effective_at:'2026-07-24',freshness_status:'fresh',normalization_warnings:[]}], warnings:[], capability_status:{identity:'available',nav:'available'},
      qdii_context:{latest_market_move_reflected:'unknown'}, trust:{level:'trusted',executable:true,critical_ready:true,reason_codes:['QDII_DATA_LAG'],warnings:['QDII NAV publication lag is disclosed.'],nav_lag_trading_days:1},
    }), { status: 200 })
    if (url.includes('/api/funds/016453/evaluate')) return new Response(JSON.stringify({
      snapshot: { identity: { code:'016453', display_name:'南方纳斯达克100指数(QDII)C', share_class:'C', vehicle_type:'index_feeder', strategy_type:'index', market_scope:'qdii', currency:'CNY', tags:['US / QDII'], warnings:[] }, analysis_date:'2026-07-25', retrieved_at:'2026-07-25T08:00:00+00:00', nav_history:[], transaction_status:{subscription:'开放申购',redemption:'开放赎回',observed_at:'2026-07-25T08:00:00+00:00'}, fees:[], metrics:[], evidence:[], warnings:[], capability_status:{identity:'available'}, qdii_context:{}, trust:{level:'trusted',executable:true,critical_ready:true,reason_codes:[],warnings:[]} },
      evaluation:{code:'016453',action:'subscribe',allowed_actions:['subscribe'],blocked_actions:{},executable:true,confidence:'high',reason:'Subscription is open and critical data is current.',warnings:[]}, formal_advice:{version:1},
    }), { status: 200 })
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

it('renders a China fund search, QDII warning, and deterministic operation result', async () => {
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'China Funds' }))
  fireEvent.click(screen.getByRole('button', { name: 'Search' }))
  await screen.findByText('南方纳斯达克100指数(QDII)C')
  fireEvent.click(screen.getByRole('button', { name: /南方纳斯达克100指数/ }))
  await screen.findByText('QDII published NAV can lag overseas markets. The displayed move is not an execution NAV.')
  fireEvent.change(screen.getByLabelText('Fund action'), { target: { value: 'subscribe' } })
  fireEvent.change(screen.getByLabelText('Subscription amount'), { target: { value: '1000' } })
  fireEvent.click(screen.getByRole('button', { name: 'Evaluate operation' }))
  await screen.findByText('Executable proposal')
  expect(screen.getByText('Formal advice version 1 recorded.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Use in analysis' }))
  expect(screen.getByLabelText('Symbol')).toHaveValue('016453')
})
