import { useState, useRef, useEffect, useCallback } from 'react'
import axios from 'axios'
import { getAccessToken } from '../hooks/useAuth'
import { useMeta } from '../hooks/useMeta'
import { notify } from '../utils/notify'
import { exportMarkdown, exportPDF } from '../utils/exportReport'
import { sendBrowserNotification } from '../utils/browserNotify'
import {
  Loader2, CheckCircle, AlertCircle, History,
  X, BarChart2, Terminal, FileText, Zap, Square,
  Download, FileDown,
} from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────
interface WsEvent {
  type: string; section?: string; content?: string; signal?: string
  final_decision?: string; message?: string; duration_seconds?: number
  llm_calls?: number; status?: string; agent?: string; analysis_id?: number
  label?: string; stage?: string; node?: string  // type === 'progress'
}
interface HistoryItem {
  id: number; ticker: string; trade_date: string; asset_type: string
  signal: string | null; duration_seconds: number; triggered_by: string; created_at: string
}
interface AnalysisDetail {
  id: number; ticker: string; trade_date: string; signal: string | null
  market_report: string; sentiment_report: string; news_report: string
  fundamentals_report: string; macro_report: string; options_report: string
  quant_report: string; earnings_report: string; review_report: string
  investment_plan: string; trader_plan: string; final_decision: string
  bull_history: string; bear_history: string; investment_debate_history: string
  risk_debate_history: string; judge_decision: string
  llm_calls: number; tokens_in: number; tokens_out: number; duration_seconds: number
}
interface PortfolioHistoryItem {
  id: number; tickers: string[]; trade_date: string; asset_type: string
  triggered_by: string; created_at: string
}
interface PortfolioDetail {
  id: number; tickers: string[]; trade_date: string
  super_portfolio_report: string; analysis_ids: number[]; created_at: string
}

// ── Constants ─────────────────────────────────────────────────────────────────
const STORAGE_KEY = 'ta_last_run'
const TASK_KEY = 'ta_task_running'

const SECTION_LABELS: Record<string, string> = {
  market_report: 'Piyasa Analizi', sentiment_report: 'Duygu Analizi',
  news_report: 'Haber Analizi', fundamentals_report: 'Temel Analiz',
  macro_report: 'Makro Analiz', options_report: 'Opsiyon Analizi',
  quant_report: 'Kantitatif Analiz', earnings_report: 'Kazanç Analizi',
  review_report: 'Performans İnceleme', investment_plan: 'Yatırım Planı',
  trader_investment_plan: 'Trader Planı', final_trade_decision: 'PM Kararı',
  bull_history: 'Boğa Argümanları', bear_history: 'Ayı Argümanları',
  investment_debate_history: 'Tartışma', risk_debate_history: 'Risk Tartışması',
  judge_decision: 'Hakem Kararı',
}

// Signal styling lives in the frontend (presentation), but the semantic tone
// + Turkish label come from the backend (/api/meta). tone → Tailwind classes:
const TONE_CLASSES: Record<string, { bg: string; text: string; border: string }> = {
  positive: { bg: 'bg-emerald-500/15', text: 'text-emerald-300', border: 'border-emerald-500/30' },
  neutral:  { bg: 'bg-yellow-500/15',  text: 'text-yellow-300',  border: 'border-yellow-500/30' },
  negative: { bg: 'bg-red-500/15',     text: 'text-red-300',     border: 'border-red-500/30' },
}
// Fallback value→tone used only until /api/meta has loaded.
const FALLBACK_TONE: Record<string, string> = {
  Buy: 'positive', Overweight: 'positive', Hold: 'neutral', Underweight: 'negative', Sell: 'negative',
}

// ── Shared UI helpers ─────────────────────────────────────────────────────────
function SignalBadge({ signal, large }: { signal: string | null; large?: boolean }) {
  const meta = useMeta()
  if (!signal) return null
  const sig = meta?.signals.find(s => s.value === signal)
  const tone = sig?.tone ?? FALLBACK_TONE[signal]
  const m = tone ? TONE_CLASSES[tone] : undefined
  const label = sig?.label ?? signal
  if (!m) return <span className="text-gray-400">{label}</span>
  return (
    <span className={`inline-flex items-center font-bold border rounded-xl ${m.bg} ${m.text} ${m.border} ${large ? 'px-4 py-1.5 text-base' : 'px-2.5 py-0.5 text-xs'}`}>
      {label}
    </span>
  )
}

function ReportCard({ label, content, defaultOpen }: { label: string; content: string; defaultOpen?: boolean }) {
  if (!content) return null
  return (
    <details open={defaultOpen} className="group">
      <summary className="flex items-center gap-2 cursor-pointer select-none px-4 py-3 rounded-xl bg-gray-800/60 hover:bg-gray-800 transition-colors border border-gray-700/50 list-none">
        <FileText size={13} className="text-violet-400 shrink-0" />
        <span className="text-sm font-medium text-gray-200 flex-1">{label}</span>
        <span className="text-xs text-gray-500 group-open:hidden">Göster</span>
        <span className="text-xs text-gray-500 hidden group-open:inline">Gizle</span>
      </summary>
      <pre className="text-xs text-gray-300 whitespace-pre-wrap bg-gray-900/80 rounded-xl p-4 mt-1.5 max-h-72 overflow-y-auto border border-gray-700/30 font-mono leading-relaxed">
        {content}
      </pre>
    </details>
  )
}

// ── Tab: Single-ticker run ────────────────────────────────────────────────────
const EMPTY_RUN = {
  ticker: '', date: new Date().toISOString().slice(0, 10), assetType: 'stock',
  runStatus: 'idle' as 'idle' | 'running' | 'done' | 'error',
  signal: null as string | null, reports: {} as Record<string, string>,
  log: [] as string[], activeSection: null as string | null,
}

function loadRunState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const hasRunningTask = !!localStorage.getItem(TASK_KEY)
    if (!raw) return EMPTY_RUN
    const parsed = JSON.parse(raw)
    if (hasRunningTask) {
      return { ...EMPTY_RUN, ...parsed, runStatus: 'running' }
    }
    const status = parsed.runStatus === 'running' ? 'idle' : parsed.runStatus
    return { ...EMPTY_RUN, ...parsed, runStatus: status }
  } catch { return EMPTY_RUN }
}

function RunTab() {
  const saved = loadRunState()
  const [ticker, setTicker] = useState(saved.ticker)
  const [date, setDate] = useState(saved.date)
  const [assetType, setAssetType] = useState(saved.assetType)
  const [running, setRunning] = useState(saved.runStatus === 'running')
  const [runStatus, setRunStatus] = useState<'idle' | 'running' | 'done' | 'error'>(saved.runStatus)
  const [signal, setSignal] = useState<string | null>(saved.signal)
  const [reports, setReports] = useState<Record<string, string>>(saved.reports)
  const [log, setLog] = useState<string[]>(saved.log)
  const [activeSection, setActiveSection] = useState<string | null>(saved.activeSection)
  const wsRef = useRef<WebSocket | null>(null)
  const taskIdRef = useRef<string | null>(null)
  const preRefreshLogRef = useRef<string[] | null>(null)

  const meta = useMeta()
  const sectionLabels = meta?.section_labels ?? SECTION_LABELS
  const assetTypes = meta?.asset_types ?? [{ value: 'stock', label: 'Hisse' }, { value: 'crypto', label: 'Kripto' }]
  const [currentStep, setCurrentStep] = useState<{ label: string; stage: string } | null>(null)

  // Cost estimate (MOD8)
  const [costEstimate, setCostEstimate] = useState<{ min_usd: number; max_usd: number } | null>(null)
  // Re-analysis warning (MOD8)
  const [existingId, setExistingId] = useState<number | null>(null)
  const [showRerunModal, setShowRerunModal] = useState(false)

  // Persist state to localStorage on every change
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ticker, date, assetType, runStatus, signal, reports, log, activeSection }))
  }, [ticker, date, assetType, runStatus, signal, reports, log, activeSection])

  const setRunning_ = (v: boolean) => {
    setRunning(v)
    if (!v) {
      localStorage.removeItem(TASK_KEY)
      taskIdRef.current = null
    }
  }

  // ── Shared WS attachment (used by handleRun AND auto-reconnect) ─────────────
  const attachWs = useCallback((taskId: string, isReconnect = false) => {
    taskIdRef.current = taskId
    const token = getAccessToken()
    const ws = new WebSocket(`/ws/analysis/${taskId}?token=${token}`)
    wsRef.current = ws
    let finished = false

    const appendLog = (line: string) => {
      if (preRefreshLogRef.current && preRefreshLogRef.current.length > 0) {
        const expected = preRefreshLogRef.current[0]
        if (expected === line) {
          preRefreshLogRef.current.shift()
          return
        } else {
          // Clear deduplication if mismatch or sequence completed/diverged
          preRefreshLogRef.current = []
        }
      }
      setLog(l => [...l, line])
    }

    ws.onmessage = (e) => {
      const ev: WsEvent = JSON.parse(e.data)
      if (ev.type === 'status') {
        appendLog(`${ev.agent}`)
      } else if (ev.type === 'progress') {
        // Live "which agent is running now" feedback.
        setCurrentStep({ label: ev.label || '', stage: ev.stage || '' })
        appendLog(`▸ ${ev.label}`)
      } else if (ev.type === 'report' && ev.section && ev.content) {
        setReports(r => ({ ...r, [ev.section!]: ev.content! }))
        setActiveSection(ev.section)
        appendLog(`✓ ${SECTION_LABELS[ev.section!] || ev.section}`)
      } else if (ev.type === 'decision') {
        setSignal(ev.signal || null)
      } else if (ev.type === 'complete') {
        finished = true
        setRunStatus('done')
        setRunning_(false)
        setCurrentStep(null)
        appendLog(`— Tamamlandı ${ev.duration_seconds}s / ${ev.llm_calls} LLM çağrısı`)
        sendBrowserNotification(`${ticker.toUpperCase()} analizi tamamlandı`, `Sinyal: ${ev.signal ?? 'N/A'} • ${ev.duration_seconds?.toFixed(0)}s`)
      } else if (ev.type === 'error') {
        finished = true
        setRunStatus('error')
        setRunning_(false)
        setCurrentStep(null)
        appendLog(`✗ HATA: ${ev.message}`)
        notify('error', ev.message ?? 'Analiz başarısız.', 'Analiz Hatası')
      }
    }
    ws.onerror = () => {
      if (!finished) {
        setRunStatus('error'); setRunning_(false)
        setLog(l => [...l, '✗ Bağlantı hatası.'])
        notify('error', 'WebSocket bağlantısı kesildi.', 'Analiz Hatası')
      }
    }
    ws.onclose = () => {
      if (!finished) {
        if (isReconnect) {
          // Task likely completed while page was refreshed
          setRunStatus('idle')
          setRunning_(false)
          setLog(l => [...l, '— Analiz tamamlanmış veya bağlantı kesildi. Geçmiş sekmesini kontrol et.'])
        } else {
          setRunStatus('error')
          setRunning_(false)
          const msg = 'Bağlantı kapandı — backend hatası veya LLM API anahtarı eksik olabilir.'
          setLog(l => [...l, `✗ ${msg}`])
          notify('error', msg, 'Analiz Kesildi')
        }
      }
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Auto-reconnect on page refresh if task was running ──────────────────────
  useEffect(() => {
    const raw = localStorage.getItem(TASK_KEY)
    if (!raw) return
    try {
      const { taskId, ticker: runTicker } = JSON.parse(raw)
      if (!taskId) return
      preRefreshLogRef.current = [...log]
      setRunning(true)
      setRunStatus('running')
      if (runTicker) setTicker(runTicker)
      attachWs(taskId, true)
    } catch { localStorage.removeItem(TASK_KEY) }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Cost estimate (debounced) ────────────────────────────────────────────────
  useEffect(() => {
    if (!ticker.trim() || running) return
    const tid = setTimeout(async () => {
      try {
        const { data } = await axios.get('/api/analysis/cost-estimate', { params: { ticker: ticker.toUpperCase(), trade_date: date } })
        setCostEstimate(data)
      } catch { setCostEstimate(null) }
    }, 600)
    return () => clearTimeout(tid)
  }, [ticker, date, running])

  // ── Re-analysis check ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!ticker.trim()) { setExistingId(null); return }
    const tid = setTimeout(async () => {
      try {
        const { data } = await axios.get('/api/analysis/history', { params: { limit: 5 } })
        const match = data.find((x: HistoryItem) => x.ticker === ticker.toUpperCase() && x.trade_date === date)
        setExistingId(match?.id ?? null)
      } catch { setExistingId(null) }
    }, 400)
    return () => clearTimeout(tid)
  }, [ticker, date])

  // Stop: close WS + cancel backend task
  const handleStop = async () => {
    const tid = taskIdRef.current
    wsRef.current?.close()
    wsRef.current = null
    setRunStatus('idle')
    setRunning_(false)
    setLog(l => [...l, '— Analiz durduruldu.'])
    if (tid) {
      try { await axios.post(`/api/analysis/${tid}/cancel`) } catch { /* ignore */ }
    }
  }

  const doRun = async () => {
    setShowRerunModal(false)
    setRunning(true)
    setRunStatus('running')
    setSignal(null)
    setReports({})
    setLog([])
    setActiveSection(null)
    setCurrentStep(null)
    preRefreshLogRef.current = null

    try {
      const { data } = await axios.post('/api/analysis/run', {
        ticker: ticker.toUpperCase(), trade_date: date, asset_type: assetType,
      })
      const taskId = data.task_id
      localStorage.setItem(TASK_KEY, JSON.stringify({ ticker: ticker.toUpperCase(), taskId, startedAt: new Date().toISOString() }))
      attachWs(taskId, false)
    } catch (err: any) {
      setRunStatus('error')
      setRunning_(false)
      setLog(l => [...l, `✗ ${err.response?.data?.detail || 'Başlatılamadı'}`])
    }
  }

  const handleRun = () => {
    if (!ticker.trim()) return
    if (existingId) { setShowRerunModal(true); return }
    doRun()
  }

  const handleClear = () => {
    setRunStatus('idle'); setSignal(null); setReports({}); setLog([]); setActiveSection(null); setCurrentStep(null)
  }

  const reportEntries = Object.entries(reports)

  return (
    <div className="space-y-4">
      {/* Form card */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 md:p-5">
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs font-medium text-gray-500 mb-1.5 block uppercase tracking-wider">Sembol</label>
            <input
              className="bg-gray-800 border border-gray-700 text-white rounded-xl px-3 py-2 w-28 uppercase font-mono text-sm focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none transition"
              value={ticker}
              onChange={e => setTicker(e.target.value.toUpperCase())}
              placeholder="AAPL"
              disabled={running}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500 mb-1.5 block uppercase tracking-wider">Tarih</label>
            <input
              type="date"
              className="bg-gray-800 border border-gray-700 text-white rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none transition"
              value={date}
              onChange={e => setDate(e.target.value)}
              disabled={running}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500 mb-1.5 block uppercase tracking-wider">Tür</label>
            <select
              className="bg-gray-800 border border-gray-700 text-white rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none transition"
              value={assetType}
              onChange={e => setAssetType(e.target.value)}
              disabled={running}
            >
              {assetTypes.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>

          {!running ? (
            <button
              onClick={handleRun}
              disabled={!ticker.trim()}
              className="flex items-center gap-2 px-5 py-2 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-violet-500/20 transition-all"
            >
              <Zap size={15} /> Analiz Başlat
            </button>
          ) : (
            <button
              onClick={handleStop}
              className="flex items-center gap-2 px-5 py-2 rounded-xl text-sm font-semibold text-white bg-red-600/80 hover:bg-red-600 border border-red-500/40 shadow-lg shadow-red-500/20 transition-all"
            >
              <Square size={13} fill="currentColor" /> Durdur
            </button>
          )}

          {runStatus !== 'idle' && !running && (
            <button onClick={handleClear} className="text-gray-600 hover:text-gray-400 transition-colors p-2 rounded-lg hover:bg-gray-800">
              <X size={14} />
            </button>
          )}

          {runStatus === 'done' && <CheckCircle size={18} className="text-emerald-400" />}
          {runStatus === 'error' && <AlertCircle size={18} className="text-red-400" />}
          {signal && <SignalBadge signal={signal} large />}
        </div>
        {/* Cost estimate + existing analysis hint */}
        {!running && (
          <div className="flex items-center gap-4 mt-2">
            {costEstimate && (
              <span className="text-xs text-gray-600">
                Tahmini maliyet: ~${costEstimate.min_usd.toFixed(3)}–${costEstimate.max_usd.toFixed(3)}
              </span>
            )}
            {existingId && (
              <span className="text-xs text-yellow-500">⚠ Bu tarih için kayıtlı analiz var — yeniden çalıştıracaksınız</span>
            )}
          </div>
        )}
      </div>

      {/* Re-run warning modal */}
      {showRerunModal && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 max-w-sm w-full space-y-4">
            <h3 className="text-white font-semibold">Mevcut Analiz Var</h3>
            <p className="text-gray-400 text-sm">{ticker.toUpperCase()} için {date} tarihli bir analiz zaten mevcut. Yeni analiz daha fazla API kredisi harcayacak.</p>
            <div className="flex gap-3">
              <button onClick={doRun} className="flex-1 bg-violet-600 hover:bg-violet-500 text-white text-sm py-2 rounded-xl transition">Yeniden Çalıştır</button>
              <button onClick={() => setShowRerunModal(false)} className="flex-1 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm py-2 rounded-xl transition">İptal</button>
            </div>
          </div>
        </div>
      )}

      {/* Running status banner */}
      {running && (
        <div className="flex items-center gap-3 px-5 py-3 bg-violet-500/10 border border-violet-500/20 rounded-2xl">
          <span className="relative flex h-2.5 w-2.5 shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-violet-500" />
          </span>
          <Loader2 size={14} className="text-violet-400 animate-spin" />
          <p className="text-violet-300 text-sm font-medium">
            <span className="font-bold">{ticker}</span> analiz ediliyor
            {currentStep
              ? <span className="text-white ml-2 font-semibold">→ {currentStep.label}</span>
              : <span className="text-violet-500 ml-2 font-normal">{log.at(-1)}</span>}
          </p>
        </div>
      )}

      {/* Content: log + reports */}
      {(log.length > 0 || reportEntries.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Terminal log */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-800 bg-gray-800/40">
              <Terminal size={13} className="text-gray-500" />
              <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">Canlı Log</span>
              <span className="ml-auto text-xs text-gray-600">{log.length} satır</span>
            </div>
            <div className="px-4 py-3 space-y-1 max-h-48 md:max-h-80 overflow-y-auto">
              {log.map((line, i) => (
                <p key={i} className={`text-xs font-mono leading-relaxed ${
                  line.startsWith('✗') ? 'text-red-400' :
                  line.startsWith('✓') ? 'text-emerald-400' :
                  line.startsWith('—') ? 'text-violet-400 font-semibold' : 'text-gray-500'
                }`}>
                  {line}
                </p>
              ))}
              {running && <p className="text-xs text-gray-600 animate-pulse font-mono">▋</p>}
            </div>
          </div>

          {/* Reports */}
          <div className="lg:col-span-2 bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-800 bg-gray-800/40">
              <FileText size={13} className="text-gray-500" />
              <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">Raporlar</span>
              <span className="ml-auto text-xs text-gray-600">{reportEntries.length} bölüm</span>
            </div>
            <div className="p-4 space-y-1.5 max-h-64 md:max-h-80 overflow-y-auto">
              {reportEntries.length === 0 && (
                <p className="text-gray-600 text-sm text-center py-8">Raporlar analiz sırasında burada görünecek.</p>
              )}
              {reportEntries.map(([section, content]) => (
                <ReportCard key={section} label={sectionLabels[section] || section} content={content} defaultOpen={section === activeSection} />
              ))}
            </div>
          </div>
        </div>
      )}
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
  const meta = useMeta()
  const assetTypes = meta?.asset_types ?? [{ value: 'stock', label: 'Hisse' }, { value: 'crypto', label: 'Kripto' }]

  const addTicker = () => {
    const t = input.trim().toUpperCase()
    if (t && !tickers.includes(t) && tickers.length < 10) setTickers(prev => [...prev, t])
    setInput('')
  }
  const handleKeyDown = (e: React.KeyboardEvent) => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTicker() } }

  const handleRun = async () => {
    if (tickers.length < 2) return
    setRunning(true); setDone(false); setError(null)
    try {
      await axios.post('/api/analysis/run-portfolio', { tickers, trade_date: date, asset_type: assetType })
      setDone(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Portföy analizi başlatılamadı.')
    } finally { setRunning(false) }
  }

  return (
    <div className="space-y-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 space-y-4">
        <p className="text-gray-500 text-sm">En az 2, en fazla 10 hisse. SuperPortfolioManager tüm hisseleri analiz edip portföy dağılımı önerir.</p>

        <div>
          <label className="text-xs font-medium text-gray-500 mb-1.5 block uppercase tracking-wider">Semboller</label>
          <div className="flex flex-wrap gap-2 min-h-11 bg-gray-800 border border-gray-700 rounded-xl px-3 py-2 focus-within:border-violet-500 transition-colors">
            {tickers.map(t => (
              <span key={t} className="flex items-center gap-1 bg-violet-500/20 border border-violet-500/30 text-violet-300 text-xs font-mono px-2 py-0.5 rounded-lg">
                {t}
                <button onClick={() => setTickers(p => p.filter(x => x !== t))} className="hover:text-red-400 transition-colors"><X size={10} /></button>
              </span>
            ))}
            {tickers.length < 10 && (
              <input
                className="bg-transparent text-white text-sm outline-none flex-1 min-w-16 uppercase font-mono placeholder-gray-600"
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
            <label className="text-xs font-medium text-gray-500 mb-1.5 block uppercase tracking-wider">Tarih</label>
            <input type="date" className="bg-gray-800 border border-gray-700 text-white rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent transition" value={date} onChange={e => setDate(e.target.value)} disabled={running} />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500 mb-1.5 block uppercase tracking-wider">Tür</label>
            <select className="bg-gray-800 border border-gray-700 text-white rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-violet-500 transition" value={assetType} onChange={e => setAssetType(e.target.value)} disabled={running}>
              {assetTypes.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <button
            onClick={handleRun}
            disabled={running || tickers.length < 2}
            className="flex items-center gap-2 px-5 py-2 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 disabled:opacity-40 shadow-lg shadow-violet-500/20 transition-all"
          >
            {running ? <Loader2 size={15} className="animate-spin" /> : <BarChart2 size={15} />}
            {running ? 'Çalışıyor...' : 'Portföy Analizi Başlat'}
          </button>
        </div>

        {done && <div className="flex items-center gap-2 text-emerald-400 text-sm"><CheckCircle size={15} /> Arka planda başlatıldı — "Portföy Geçmişi" tabından takip edebilirsiniz.</div>}
        {error && <div className="flex items-center gap-2 text-red-400 text-sm"><AlertCircle size={15} /> {error}</div>}
      </div>
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

  if (loading) return <div className="text-gray-500 text-sm px-1">Yükleniyor...</div>

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5">
      <h3 className="text-sm font-semibold text-gray-300 mb-3">Portföy Analizi Geçmişi</h3>
      {items.length === 0 ? <p className="text-gray-600 text-sm">Henüz portföy analizi yok.</p> : (
        <div className="space-y-1.5">
          {items.map(item => (
            <div key={item.id} onClick={() => axios.get(`/api/analysis/portfolio/${item.id}`).then(r => setDetail(r.data))}
              className="flex items-center justify-between p-3 rounded-xl bg-gray-800/60 hover:bg-gray-800 cursor-pointer transition-colors border border-gray-700/40 hover:border-gray-700">
              <div className="flex items-center gap-2">
                <span className="text-white font-mono text-sm font-semibold">{item.tickers.join(', ')}</span>
                <span className="text-gray-600 text-xs">{item.trade_date}</span>
              </div>
              <span className="text-gray-600 text-xs">{new Date(item.created_at).toLocaleDateString('tr-TR')}</span>
            </div>
          ))}
        </div>
      )}
      {detail && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-start justify-center p-4 overflow-y-auto backdrop-blur-sm">
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 w-full max-w-3xl my-8 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-white">{detail.tickers.join(', ')}</h3>
              <button onClick={() => setDetail(null)} className="text-gray-500 hover:text-white transition-colors p-1 rounded-lg hover:bg-gray-800"><X size={18} /></button>
            </div>
            <p className="text-gray-600 text-xs">{detail.trade_date} • {new Date(detail.created_at).toLocaleString('tr-TR')}</p>
            <pre className="text-sm text-gray-200 whitespace-pre-wrap bg-gray-950 rounded-xl p-5 max-h-96 overflow-y-auto border border-gray-800 font-mono leading-relaxed">
              {detail.super_portfolio_report || 'Rapor henüz hazır değil.'}
            </pre>
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
  const meta = useMeta()
  const sectionLabels = meta?.section_labels ?? SECTION_LABELS

  useEffect(() => {
    axios.get('/api/analysis/history?limit=50').then(r => setItems(r.data)).finally(() => setLoading(false))
  }, [])

  const openDetail = useCallback(async (id: number) => {
    setDetailLoading(true)
    try { const { data } = await axios.get(`/api/analysis/${id}`); setDetail(data) }
    finally { setDetailLoading(false) }
  }, [])

  if (loading) return <div className="p-8 text-gray-500 text-sm">Yükleniyor...</div>

  return (
    <div className="space-y-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
        {items.length === 0 ? (
          <p className="p-6 text-gray-600 text-sm">Henüz analiz geçmişi yok.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[480px]">
              <thead>
                <tr className="text-gray-600 text-xs uppercase tracking-wider border-b border-gray-800 bg-gray-800/30">
                  <th className="px-4 py-3 text-left">Sembol</th>
                  <th className="px-4 py-3 text-left">Tarih</th>
                  <th className="px-4 py-3 text-left">Sinyal</th>
                  <th className="px-4 py-3 text-left">Süre</th>
                  <th className="px-4 py-3 text-left hidden sm:table-cell">Kaynak</th>
                  <th className="px-4 py-3 text-left hidden md:table-cell">Zaman</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => (
                  <tr key={item.id} onClick={() => openDetail(item.id)}
                    className="border-t border-gray-800 hover:bg-gray-800/50 cursor-pointer transition-colors">
                    <td className="px-4 py-3 font-mono font-bold text-white">{item.ticker}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{item.trade_date}</td>
                    <td className="px-4 py-3"><SignalBadge signal={item.signal} /></td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{item.duration_seconds.toFixed(1)}s</td>
                    <td className="px-4 py-3 text-gray-600 text-xs hidden sm:table-cell">{item.triggered_by}</td>
                    <td className="px-4 py-3 text-gray-600 text-xs hidden md:table-cell">{new Date(item.created_at).toLocaleString('tr-TR')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {(detail || detailLoading) && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-start justify-center p-3 md:p-4 overflow-y-auto backdrop-blur-sm">
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 md:p-6 w-full max-w-4xl my-4 md:my-8 space-y-4">
            {detailLoading ? (
              <div className="flex items-center gap-2 text-gray-400"><Loader2 className="animate-spin" size={16} /> Yükleniyor...</div>
            ) : detail ? (
              <>
                <div className="flex items-start justify-between">
                  <div className="space-y-2">
                    <div className="flex items-center gap-3">
                      <h3 className="text-2xl font-bold text-white font-mono">{detail.ticker}</h3>
                      <SignalBadge signal={detail.signal} large />
                    </div>
                    <p className="text-gray-500 text-xs">{detail.trade_date} • {detail.duration_seconds.toFixed(1)}s • {detail.llm_calls} LLM • {(detail.tokens_in + detail.tokens_out).toLocaleString()} token</p>
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    <button onClick={() => exportMarkdown(detail)} className="flex items-center gap-1.5 text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 px-2.5 py-1.5 rounded-lg transition" title="Markdown İndir">
                      <Download size={12} /> MD
                    </button>
                    <button onClick={() => exportPDF(detail)} className="flex items-center gap-1.5 text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 px-2.5 py-1.5 rounded-lg transition" title="PDF İndir">
                      <FileDown size={12} /> PDF
                    </button>
                    <button onClick={() => setDetail(null)} className="text-gray-500 hover:text-white transition-colors p-1 rounded-lg hover:bg-gray-800"><X size={18} /></button>
                  </div>
                </div>
                <div className="space-y-1.5 max-h-[60vh] md:max-h-[65vh] overflow-y-auto pr-1">
                  {([
                    ['market_report', detail.market_report], ['sentiment_report', detail.sentiment_report],
                    ['news_report', detail.news_report], ['fundamentals_report', detail.fundamentals_report],
                    ['macro_report', detail.macro_report], ['options_report', detail.options_report],
                    ['quant_report', detail.quant_report], ['earnings_report', detail.earnings_report],
                    ['review_report', detail.review_report], ['investment_plan', detail.investment_plan],
                    ['trader_plan', detail.trader_plan], ['final_decision', detail.final_decision],
                    ['bull_history', detail.bull_history], ['bear_history', detail.bear_history],
                    ['judge_decision', detail.judge_decision],
                  ] as [string, string][]).map(([k, v]) => <ReportCard key={k} label={sectionLabels[k] || k} content={v} />)}
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
type Tab = 'run' | 'multi' | 'history'

export default function Analysis() {
  const [tab, setTab] = useState<Tab>('run')

  const tabs = [
    { id: 'run' as Tab,     label: 'Tek Hisse',       icon: <Zap size={13} /> },
    { id: 'multi' as Tab,   label: 'Çoklu Hisse',     icon: <BarChart2 size={13} /> },
    { id: 'history' as Tab, label: 'Geçmiş',          icon: <History size={13} /> },
  ]

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-lg md:text-xl font-bold text-white tracking-tight">Analiz</h2>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 p-1 bg-gray-900 border border-gray-800 rounded-2xl w-fit">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-3 md:px-4 py-2 rounded-xl text-sm font-medium transition-all ${
              tab === t.id ? 'bg-violet-600 text-white shadow-lg shadow-violet-500/20' : 'text-gray-500 hover:text-white'
            }`}
          >
            {t.icon} <span className="hidden sm:inline">{t.label}</span>
          </button>
        ))}
      </div>

      {tab === 'run'     && <RunTab />}
      {tab === 'multi'   && <MultiTab />}
      {tab === 'history' && <HistoryTab />}
    </div>
  )
}
