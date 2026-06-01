import { useState, useRef } from 'react'
import axios from 'axios'
import { getAccessToken } from '../hooks/useAuth'
import { Play, Loader2, CheckCircle, AlertCircle } from 'lucide-react'

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
}

const SIGNAL_COLORS: Record<string, string> = {
  Buy: 'bg-emerald-600',
  Overweight: 'bg-green-600',
  Hold: 'bg-yellow-600',
  Underweight: 'bg-orange-600',
  Sell: 'bg-red-600',
}

export default function Analysis() {
  const [ticker, setTicker] = useState('')
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [assetType, setAssetType] = useState('stock')
  const [running, setRunning] = useState(false)
  const [status, setStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle')
  const [signal, setSignal] = useState<string | null>(null)
  const [reports, setReports] = useState<Record<string, string>>({})
  const [log, setLog] = useState<string[]>([])
  const [activeSection, setActiveSection] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const handleRun = async () => {
    if (!ticker.trim()) return
    setRunning(true)
    setStatus('running')
    setSignal(null)
    setReports({})
    setLog([])
    setActiveSection(null)

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
        setStatus('done')
        setRunning(false)
        setLog(l => [...l, `Tamamlandı — ${event.duration_seconds}s, ${event.llm_calls} LLM çağrısı`])
      } else if (event.type === 'error') {
        setStatus('error')
        setRunning(false)
        setLog(l => [...l, `HATA: ${event.message}`])
      }
    }
    ws.onerror = () => { setStatus('error'); setRunning(false) }
  }

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-2xl font-bold text-white">Manuel Analiz</h2>

      {/* Input form */}
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
        {status === 'done' && <CheckCircle size={22} className="text-emerald-400" />}
        {status === 'error' && <AlertCircle size={22} className="text-red-400" />}
        {signal && (
          <span className={`px-3 py-1 rounded-full text-white font-bold text-sm ${SIGNAL_COLORS[signal] || 'bg-slate-600'}`}>
            {signal}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Progress log */}
        <div className="bg-slate-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Canlı Log</h3>
          <div className="text-xs font-mono text-slate-400 space-y-1 max-h-96 overflow-y-auto">
            {log.length === 0 && <p className="text-slate-600">Analiz başlatıldığında log burada görünür.</p>}
            {log.map((l, i) => <p key={i}>{l}</p>)}
          </div>
        </div>

        {/* Reports */}
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
