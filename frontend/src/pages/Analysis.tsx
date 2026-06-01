import { useState, useRef, useEffect, useCallback } from 'react'
import axios from 'axios'
import { getAccessToken } from '../hooks/useAuth'
import {
  Play, Loader2, CheckCircle, AlertCircle, History,
  ChevronDown, ChevronUp, X, Plus, BarChart2,
} from 'lucide-react'

interface WsEvent {
  type: string
  section?: string
  content?: string
  signal?: string
  final_decision?: string
  message?: string
  duration_seconds?: number
  llm_calls?: number
  status?: string
  agent?: string
  analysis_id?: number
}

interface HistoryItem {
  id: number
  ticker: string
  trade_date: string
  asset_type: string
  signal: string | null
  duration_seconds: number
  triggered_by: string
  created_at: string
}

interface AnalysisDetail {
  id: number
  ticker: string
  trade_date: string
  signal: string | null
  market_report: string
  sentiment_report: string
  news_report: string
  fundamentals_report: string
  macro_report: string
  options_report: string
  quant_report: string
  earnings_report: string
  review_report: string
  investment_plan: string
  trader_plan: string
  final_decision: string
  bull_history: string
  bear_history: string
  investment_debate_history: string
  risk_debate_history: string
  judge_decision: string
  llm_calls: number
  tokens_in: number
  tokens_out: number
  duration_seconds: number
}

interface PortfolioHistoryItem {
  id: number
  tickers: string[]
  trade_date: string
  asset_type: string
  triggered_by: string
  created_at: string
}

interface PortfolioDetail {
  id: number
  tickers: string[]
  trade_date: string
  super_portfolio_report: string
  analysis_ids: number[]
  created_at: string
}

const SECTION_LABELS: Record<string, string> = {
  market_report: 'Piyasa Analizi',
  sentiment_report: 'Duygu Analizi',
  news_report: 'Haber Analizi',
  fundamentals_report: 'Temel Analiz',
  macro_report: 'Makro Analiz',
  options_report: 'Opsiyon Analizi',
  quant_report: 'Kantitatif Analiz',
  earnings_report: 'Kazanç Analizi',
  review_report: 'Performans İnceleme',
  investment_plan: 'Yatırım Planı',
  trader_investment_plan: 'Trader Planı',
  final_trade_decision: 'Portfolio Yönetici Kararı',
  bull_history: 'Boğa Argümanları',
  bear_history: 'Ayı Argümanları',
  investment_debate_history: 'Tartışma Geçmişi',
  risk_debate_history: 'Risk Tartışması',
  judge_decision: 'Hakem Kararı',
}

const SIGNAL_COLORS: Record<string, string> = {
  Buy: 'bg-emerald-600',
  Overweight: 'bg-green-600',
  Hold: 'bg-yellow-600',
  Underweight: 'bg-orange-600',
  Sell: 'bg-red-600',
}

function SignalBadge({ signal }: { signal: string | null }) {
  if (!signal) return null
  return (
    <span className={`px-3 py-1 rounded-full text-white font-bold text-sm ${SIGNAL_COLORS[signal] || 'bg-slate-600'}`}>
      {signal}
    </span>
  )
}

function ReportSection({ label, content }: { label: string; content: string }) {
  if (!content) return null
  return (
    <details>
      <summary className="cursor-pointer text-sm font-semibold text-indigo-300 py-1 flex items-center gap-1">
        {label}
      </summary>
      <pre className="text-xs text-slate-300 whitespace-pre-wrap bg-slate-900 rounded-lg p-3 mt-1 max-h-64 overflow-y-auto">
        {content}
      </pre>
    </details>
  )
}

// ── Tab: Single-ticker run ────────────────────────────────────────────────────
function RunTab() {
  const [ticker, setTicker] = useState('')
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [assetType, setAssetType] = useState('stock')
  const [running, setRunning] = useState(false)
  const [runStatus, setRunStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle')
  const [signal, setSignal] = useState<string | null>(null)
  const [reports, setReports] = useState<Record<string, string>>({})
  const [log, setLog] = useState<string[]>([])
  const [activeSection, setActiveSection] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const handleRun = async () => {
    if (!ticker.trim()) return
    setRunning(true)
    setRunStatus('running')
    setSignal(null)
    setReports({})
    setLog([])
    setActiveSection(null)

    try {
      const { data } = await axios.post('/api/analysis/run', {
        ticker: ticker.toUpperCase(),
        trade_date: date,
        asset_type: assetType,
      })

      const taskId = data.task_id
      const token = getAccessToken()
      const ws = new WebSocket(`/ws/analysis/${taskId}?token=${token}`)
      wsRef.current = ws

      ws.onmessage = (e) => {
        const event: WsEvent = JSON.parse(e.data)
        if (event.type === 'status') {
          setLog(l => [...l, `[${event.status}] ${event.agent}`])
        } else if (event.type === 'report' && event.section && event.content) {
          setReports(r => ({ ...r, [event.section!]: event.content! }))
          setActiveSection(event.section)
          setLog(l => [...l, `Rapor hazır: ${SECTION_LABELS[event.section!] || event.section}`])
        } else if (event.type === 'decision') {
          setSignal(event.signal || null)
        } else if (event.type === 'complete') {
          setRunStatus('done')
          setRunning(false)
          setLog(l => [...l, `Tamamlandı — ${event.duration_seconds}s, ${event.llm_calls} LLM çağrısı`])
        } else if (event.type === 'error') {
          setRunStatus('error')
          setRunning(false)
          setLog(l => [...l, `HATA: ${event.message}`])
        }
      }
      ws.onerror = () => { setRunStatus('error'); setRunning(false) }
    } catch {
      setRunStatus('error')
      setRunning(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-slate-800 rounded-xl p-5 flex flex-wrap gap-3 items-end">
        <div>
          <label className="text-xs text-slate-400 mb-1 block">Sembol</label>
          <input
            className="bg-slate-700 text-white rounded-lg px-3 py-2 w-32 uppercase font-mono focus:ring-2 focus:ring-indigo-500 outline-none"
            value={ticker}
            onChange={e => setTicker(e.target.value.toUpperCase())}
            placeholder="AAPL"
            disabled={running}
          />
        </div>
        <div>
          <label className="text-xs text-slate-400 mb-1 block">Tarih</label>
          <input
            type="date"
            className="bg-slate-700 text-white rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 outline-none"
            value={date}
            onChange={e => setDate(e.target.value)}
            disabled={running}
          />
        </div>
        <div>
          <label className="text-xs text-slate-400 mb-1 block">Varlık Tipi</label>
          <select
            className="bg-slate-700 text-white rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 outline-none"
            value={assetType}
            onChange={e => setAssetType(e.target.value)}
            disabled={running}
          >
            <option value="stock">Hisse</option>
            <option value="crypto">Kripto</option>
          </select>
        </div>
        <button
          onClick={handleRun}
          disabled={running || !ticker}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg px-5 py-2 font-semibold transition"
        >
          {running ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
          {running ? 'Çalışıyor...' : 'Analiz Başlat'}
        </button>
        {runStatus === 'done' && <CheckCircle size={22} className="text-emerald-400" />}
        {runStatus === 'error' && <AlertCircle size={22} className="text-red-400" />}
        <SignalBadge signal={signal} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-slate-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Canlı Log</h3>
          <div className="text-xs font-mono text-slate-400 space-y-1 max-h-96 overflow-y-auto">
            {log.length === 0 && <p className="text-slate-600">Analiz başlatıldığında log burada görünür.</p>}
            {log.map((l, i) => <p key={i}>{l}</p>)}
          </div>
        </div>
        <div className="lg:col-span-2 bg-slate-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Raporlar</h3>
          {Object.keys(reports).length === 0 && (
            <p className="text-slate-600 text-sm">Analiz raporları burada görünecek.</p>
          )}
          <div className="space-y-2">
            {Object.entries(reports).map(([section, content]) => (
              <details key={section} open={section === activeSection}>
                <summary className="cursor-pointer text-sm font-semibold text-indigo-300 py-1">
                  {SECTION_LABELS[section] || section}
                </summary>
                <pre className="text-xs text-slate-300 whitespace-pre-wrap bg-slate-900 rounded-lg p-3 mt-1 max-h-64 overflow-y-auto">
                  {content}
                </pre>
              </details>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Tab: Multi-ticker portfolio run ──────────────────────────────────────────
function MultiTab() {
  const [tickers, setTickers] = useState<string[]>([])
  const [input, setInput] = useState('')
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [assetType, setAssetType] = useState('stock')
  const [running, setRunning] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const addTicker = () => {
    const t = input.trim().toUpperCase()
    if (t && !tickers.includes(t) && tickers.length < 10) {
      setTickers(prev => [...prev, t])
    }
    setInput('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTicker() }
  }

  const handleRun = async () => {
    if (tickers.length < 2) return
    setRunning(true)
    setDone(false)
    setError(null)
    try {
      await axios.post('/api/analysis/run-portfolio', {
        tickers,
        trade_date: date,
        asset_type: assetType,
      })
      setDone(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Portföy analizi başlatılamadı.')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-slate-800 rounded-xl p-5 space-y-4">
        <p className="text-slate-400 text-sm">
          Birden fazla hisse girin (en az 2, en fazla 10). SuperPortfolioManager tüm hisseler için
          analiz yaptıktan sonra portföy dağılımı önerir.
        </p>

        {/* Ticker tags */}
        <div>
          <label className="text-xs text-slate-400 mb-1 block">Semboller</label>
          <div className="flex flex-wrap gap-2 min-h-10 bg-slate-700 rounded-lg px-3 py-2 border border-slate-600 focus-within:border-indigo-500">
            {tickers.map(t => (
              <span key={t} className="flex items-center gap-1 bg-indigo-700 text-white text-xs font-mono px-2 py-0.5 rounded">
                {t}
                <button onClick={() => setTickers(prev => prev.filter(x => x !== t))} className="hover:text-red-300">
                  <X size={10} />
                </button>
              </span>
            ))}
            {tickers.length < 10 && (
              <input
                className="bg-transparent text-white text-sm outline-none flex-1 min-w-16 uppercase font-mono"
                placeholder="AAPL, Enter"
                value={input}
                onChange={e => setInput(e.target.value.toUpperCase())}
                onKeyDown={handleKeyDown}
                onBlur={addTicker}
              />
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-slate-400 mb-1 block">Tarih</label>
            <input
              type="date"
              className="bg-slate-700 text-white rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 outline-none"
              value={date}
              onChange={e => setDate(e.target.value)}
              disabled={running}
            />
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">Varlık Tipi</label>
            <select
              className="bg-slate-700 text-white rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 outline-none"
              value={assetType}
              onChange={e => setAssetType(e.target.value)}
              disabled={running}
            >
              <option value="stock">Hisse</option>
              <option value="crypto">Kripto</option>
            </select>
          </div>
          <button
            onClick={handleRun}
            disabled={running || tickers.length < 2}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg px-5 py-2 font-semibold transition"
          >
            {running ? <Loader2 size={16} className="animate-spin" /> : <BarChart2 size={16} />}
            {running ? 'Çalışıyor...' : 'Portföy Analizi Başlat'}
          </button>
        </div>

        {done && (
          <div className="flex items-center gap-2 text-emerald-400 text-sm">
            <CheckCircle size={16} />
            Analiz arka planda başlatıldı. Sonuçlar için "Portföy Geçmişi" sekmesini kontrol edin.
          </div>
        )}
        {error && (
          <div className="flex items-center gap-2 text-red-400 text-sm">
            <AlertCircle size={16} /> {error}
          </div>
        )}
      </div>

      {/* Portfolio history inline */}
      <PortfolioHistorySection />
    </div>
  )
}

function PortfolioHistorySection() {
  const [items, setItems] = useState<PortfolioHistoryItem[]>([])
  const [detail, setDetail] = useState<PortfolioDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    axios.get('/api/analysis/portfolio-history').then(r => setItems(r.data)).finally(() => setLoading(false))
  }, [])

  const openDetail = async (id: number) => {
    const { data } = await axios.get(`/api/analysis/portfolio/${id}`)
    setDetail(data)
  }

  if (loading) return <div className="text-slate-400 text-sm">Yükleniyor...</div>

  return (
    <div className="bg-slate-800 rounded-xl p-5">
      <h3 className="text-base font-semibold text-white mb-3">Portföy Analizi Geçmişi</h3>
      {items.length === 0 ? (
        <p className="text-slate-500 text-sm">Henüz portföy analizi yok.</p>
      ) : (
        <div className="space-y-2">
          {items.map(item => (
            <div key={item.id}
              className="border border-slate-700 rounded-lg p-3 cursor-pointer hover:bg-slate-700 transition"
              onClick={() => openDetail(item.id)}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-white font-mono text-sm font-bold">{item.tickers.join(', ')}</span>
                  <span className="text-slate-500 text-xs">{item.trade_date}</span>
                </div>
                <span className="text-slate-400 text-xs">{new Date(item.created_at).toLocaleDateString('tr-TR')}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Detail modal */}
      {detail && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-start justify-center p-4 overflow-y-auto">
          <div className="bg-slate-800 rounded-xl p-6 w-full max-w-3xl my-8 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-white">{detail.tickers.join(', ')} — Portföy Analizi</h3>
              <button onClick={() => setDetail(null)} className="text-slate-400 hover:text-white">
                <X size={20} />
              </button>
            </div>
            <p className="text-slate-400 text-xs">{detail.trade_date} • {new Date(detail.created_at).toLocaleString('tr-TR')}</p>
            <div>
              <h4 className="text-sm font-semibold text-indigo-300 mb-2">Portföy Dağılım Önerisi</h4>
              <pre className="text-sm text-slate-200 whitespace-pre-wrap bg-slate-900 rounded-lg p-4 max-h-96 overflow-y-auto">
                {detail.super_portfolio_report || 'Rapor henüz hazır değil.'}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Tab: History ──────────────────────────────────────────────────────────────
function HistoryTab() {
  const [items, setItems] = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [detail, setDetail] = useState<AnalysisDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    axios.get('/api/analysis/history?limit=50')
      .then(r => setItems(r.data))
      .finally(() => setLoading(false))
  }, [])

  const openDetail = useCallback(async (id: number) => {
    setDetailLoading(true)
    try {
      const { data } = await axios.get(`/api/analysis/${id}`)
      setDetail(data)
    } finally {
      setDetailLoading(false)
    }
  }, [])

  if (loading) return <div className="p-8 text-slate-400">Yükleniyor...</div>

  return (
    <div className="space-y-4">
      <div className="bg-slate-800 rounded-xl overflow-hidden">
        {items.length === 0 ? (
          <p className="p-6 text-slate-500 text-sm">Henüz analiz geçmişi yok.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 text-xs text-left border-b border-slate-700">
                <th className="px-4 py-3">Sembol</th>
                <th className="px-4 py-3">Tarih</th>
                <th className="px-4 py-3">Sinyal</th>
                <th className="px-4 py-3">Süre</th>
                <th className="px-4 py-3">Tetikleyen</th>
                <th className="px-4 py-3">Oluşturulma</th>
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <tr
                  key={item.id}
                  className="border-t border-slate-700 hover:bg-slate-700/50 cursor-pointer transition"
                  onClick={() => openDetail(item.id)}
                >
                  <td className="px-4 py-3 font-mono font-bold text-white">{item.ticker}</td>
                  <td className="px-4 py-3 text-slate-300">{item.trade_date}</td>
                  <td className="px-4 py-3">
                    {item.signal ? (
                      <span className={`px-2 py-0.5 rounded-full text-white text-xs font-bold ${SIGNAL_COLORS[item.signal] || 'bg-slate-600'}`}>
                        {item.signal}
                      </span>
                    ) : <span className="text-slate-500">—</span>}
                  </td>
                  <td className="px-4 py-3 text-slate-400">{item.duration_seconds.toFixed(1)}s</td>
                  <td className="px-4 py-3 text-slate-400">{item.triggered_by}</td>
                  <td className="px-4 py-3 text-slate-400">
                    {new Date(item.created_at).toLocaleString('tr-TR')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Detail panel */}
      {(detail || detailLoading) && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-start justify-center p-4 overflow-y-auto">
          <div className="bg-slate-800 rounded-xl p-6 w-full max-w-4xl my-8 space-y-4">
            {detailLoading ? (
              <div className="flex items-center gap-2 text-slate-400"><Loader2 className="animate-spin" size={18} /> Yükleniyor...</div>
            ) : detail ? (
              <>
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center gap-3">
                      <h3 className="text-xl font-bold text-white font-mono">{detail.ticker}</h3>
                      <SignalBadge signal={detail.signal} />
                    </div>
                    <p className="text-slate-400 text-xs">
                      {detail.trade_date} • {detail.duration_seconds.toFixed(1)}s • {detail.llm_calls} LLM çağrısı •
                      {detail.tokens_in + detail.tokens_out} token
                    </p>
                  </div>
                  <button onClick={() => setDetail(null)} className="text-slate-400 hover:text-white ml-4">
                    <X size={20} />
                  </button>
                </div>

                <div className="space-y-2 max-h-[70vh] overflow-y-auto pr-1">
                  {([
                    ['market_report', detail.market_report],
                    ['sentiment_report', detail.sentiment_report],
                    ['news_report', detail.news_report],
                    ['fundamentals_report', detail.fundamentals_report],
                    ['macro_report', detail.macro_report],
                    ['options_report', detail.options_report],
                    ['quant_report', detail.quant_report],
                    ['earnings_report', detail.earnings_report],
                    ['review_report', detail.review_report],
                    ['investment_plan', detail.investment_plan],
                    ['trader_plan', detail.trader_plan],
                    ['final_decision', detail.final_decision],
                    ['bull_history', detail.bull_history],
                    ['bear_history', detail.bear_history],
                    ['judge_decision', detail.judge_decision],
                  ] as [string, string][]).map(([key, val]) => (
                    <ReportSection key={key} label={SECTION_LABELS[key] || key} content={val} />
                  ))}
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
type Tab = 'run' | 'multi' | 'history'

export default function Analysis() {
  const [tab, setTab] = useState<Tab>('run')

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'run', label: 'Çalıştır', icon: <Play size={14} /> },
    { id: 'multi', label: 'Çoklu Hisse', icon: <BarChart2 size={14} /> },
    { id: 'history', label: 'Geçmiş', icon: <History size={14} /> },
  ]

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-2xl font-bold text-white">Analiz</h2>

      {/* Tab bar */}
      <div className="flex gap-1 bg-slate-800 rounded-xl p-1 w-fit">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition ${
              tab === t.id
                ? 'bg-indigo-600 text-white'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {tab === 'run' && <RunTab />}
      {tab === 'multi' && <MultiTab />}
      {tab === 'history' && <HistoryTab />}
    </div>
  )
}
