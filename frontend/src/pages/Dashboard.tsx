import { useEffect, useState } from 'react'
import axios from 'axios'
import { TrendingUp, TrendingDown, DollarSign, Activity, ArrowRight, Target, ExternalLink } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useMeta } from '../hooks/useMeta'

interface NewsItem { title: string; url: string; source: string; published_at: string; ticker: string }

interface Portfolio {
  id: number; mode: string; broker: string
  initial_capital: number; current_balance: number; cash_available: number
  status: string
  holdings: { ticker: string; quantity: number; current_price: number; unrealized_pnl: number }[]
}

// tone → presentation (the semantic tone + Turkish label come from /api/meta).
const TONE_META: Record<string, { text: string; dot: string }> = {
  positive: { text: 'text-emerald-400', dot: 'bg-emerald-400' },
  neutral:  { text: 'text-yellow-400',  dot: 'bg-yellow-400' },
  negative: { text: 'text-red-400',     dot: 'bg-red-400' },
}
const FALLBACK_TONE: Record<string, string> = {
  Buy: 'positive', Overweight: 'positive', Hold: 'neutral', Underweight: 'negative', Sell: 'negative',
}

function SignalBadge({ signal }: { signal: string | null }) {
  const meta = useMeta()
  if (!signal) return <span className="text-gray-600 text-xs">—</span>
  const sig = meta?.signals.find(s => s.value === signal)
  const tone = sig?.tone ?? FALLBACK_TONE[signal]
  const m = tone ? TONE_META[tone] : undefined
  const label = sig?.label ?? signal
  return (
    <span className={`flex items-center gap-1.5 text-xs font-semibold ${m?.text || 'text-gray-400'}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${m?.dot || 'bg-gray-400'}`} />
      {label}
    </span>
  )
}

export default function Dashboard() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [recentAnalysis, setRecentAnalysis] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [perf, setPerf] = useState<{ win_rate: number | null; avg_raw_return: number | null; total: number } | null>(null)
  const [news, setNews] = useState<NewsItem[]>([])
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([
      axios.get('/api/portfolio').then(r => r.data),
      axios.get('/api/analysis/history?limit=8').then(r => r.data),
      axios.get('/api/analysis/performance').then(r => r.data).catch(() => null),
    ]).then(([p, a, pf]) => { setPortfolios(p); setRecentAnalysis(a); if (pf) setPerf(pf) })
      .finally(() => setLoading(false))
  }, [])

  // Load news feed from watchlist tickers
  useEffect(() => {
    axios.get('/api/settings').then(r => {
      const tickers = (r.data.watchlist as string[]).slice(0, 5)
      if (tickers.length === 0) return
      return axios.get('/api/news/feed', { params: { tickers: tickers.join(','), limit: 3 } }).then(r => setNews(r.data))
    }).catch(() => {})
    const id = setInterval(() => {
      axios.get('/api/settings').then(r => {
        const tickers = (r.data.watchlist as string[]).slice(0, 5)
        if (tickers.length === 0) return
        return axios.get('/api/news/feed', { params: { tickers: tickers.join(','), limit: 3 } }).then(r => setNews(r.data))
      }).catch(() => {})
    }, 5 * 60 * 1000)
    return () => clearInterval(id)
  }, [])

  if (loading) {
    return (
      <div className="p-6 space-y-4">
        <div className="h-8 w-32 bg-gray-800 rounded-lg animate-pulse" />
        <div className="grid grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-gray-800 rounded-2xl animate-pulse" />)}
        </div>
      </div>
    )
  }

  const sim = portfolios.find(p => p.mode === 'simulation') || portfolios[0]
  const pnl = sim ? sim.current_balance - sim.initial_capital : 0
  const pnlPct = sim?.initial_capital ? (pnl / sim.initial_capital * 100) : 0
  const totalUnrealized = sim?.holdings.reduce((s, h) => s + h.unrealized_pnl, 0) ?? 0

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white tracking-tight">Dashboard</h2>
        <button
          onClick={() => navigate('/analysis')}
          className="flex items-center gap-1.5 text-sm text-violet-400 hover:text-violet-300 transition-colors"
        >
          Yeni Analiz <ArrowRight size={14} />
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          icon={<DollarSign size={18} />}
          label="Portföy Değeri"
          value={sim ? `$${sim.current_balance.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}` : '—'}
          color="text-white"
        />
        <KpiCard
          icon={pnl >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
          label="Toplam Getiri"
          value={`${pnl >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%`}
          sub={`${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`}
          color={pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}
          accent={pnl >= 0 ? 'from-emerald-500/10' : 'from-red-500/10'}
        />
        <KpiCard
          icon={<DollarSign size={18} />}
          label="Nakit"
          value={sim ? `$${sim.cash_available.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}` : '—'}
          color="text-white"
        />
        <KpiCard
          icon={<Activity size={18} />}
          label="Gerçekleşmemiş K/Z"
          value={`${totalUnrealized >= 0 ? '+' : ''}$${totalUnrealized.toFixed(2)}`}
          color={totalUnrealized >= 0 ? 'text-emerald-400' : 'text-red-400'}
          accent={totalUnrealized >= 0 ? 'from-emerald-500/10' : 'from-red-500/10'}
        />
        {perf && perf.total > 0 && (
          <KpiCard
            icon={<Target size={18} />}
            label="Sinyal Kazanma Oranı"
            value={perf.win_rate !== null ? `${perf.win_rate}%` : '—'}
            sub={`${perf.total} analiz`}
            color={perf.win_rate !== null && perf.win_rate >= 50 ? 'text-emerald-400' : 'text-red-400'}
            accent={perf.win_rate !== null && perf.win_rate >= 50 ? 'from-emerald-500/10' : 'from-red-500/10'}
          />
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent analyses */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
            <h3 className="text-sm font-semibold text-gray-300">Son Analizler</h3>
            <button onClick={() => navigate('/analysis')} className="text-xs text-violet-400 hover:text-violet-300 transition-colors flex items-center gap-1">
              Tümü <ArrowRight size={11} />
            </button>
          </div>
          {recentAnalysis.length === 0 ? (
            <p className="px-5 py-8 text-gray-600 text-sm text-center">Henüz analiz yapılmadı.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-600 text-xs uppercase tracking-wider bg-gray-800/30">
                  <th className="px-5 py-2.5 text-left">Sembol</th>
                  <th className="px-5 py-2.5 text-left">Tarih</th>
                  <th className="px-5 py-2.5 text-left">Sinyal</th>
                  <th className="px-5 py-2.5 text-right">Süre</th>
                </tr>
              </thead>
              <tbody>
                {recentAnalysis.map(a => (
                  <tr key={a.id}
                    onClick={() => navigate('/analysis')}
                    className="border-t border-gray-800/60 hover:bg-gray-800/40 cursor-pointer transition-colors">
                    <td className="px-5 py-3 font-mono font-bold text-white text-sm">{a.ticker}</td>
                    <td className="px-5 py-3 text-gray-500 text-xs">{a.trade_date}</td>
                    <td className="px-5 py-3"><SignalBadge signal={a.signal} /></td>
                    <td className="px-5 py-3 text-gray-600 text-xs text-right">{a.duration_seconds?.toFixed(1)}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Holdings */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
            <h3 className="text-sm font-semibold text-gray-300">Açık Pozisyonlar</h3>
            <button onClick={() => navigate('/portfolio')} className="text-xs text-violet-400 hover:text-violet-300 transition-colors flex items-center gap-1">
              Portföy <ArrowRight size={11} />
            </button>
          </div>
          {!sim?.holdings?.length ? (
            <p className="px-5 py-8 text-gray-600 text-sm text-center">Açık pozisyon yok.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-600 text-xs uppercase tracking-wider bg-gray-800/30">
                  <th className="px-5 py-2.5 text-left">Sembol</th>
                  <th className="px-5 py-2.5 text-right">Miktar</th>
                  <th className="px-5 py-2.5 text-right">Fiyat</th>
                  <th className="px-5 py-2.5 text-right">K/Z</th>
                </tr>
              </thead>
              <tbody>
                {sim.holdings.map(h => (
                  <tr key={h.ticker} className="border-t border-gray-800/60 hover:bg-gray-800/40 transition-colors">
                    <td className="px-5 py-3 font-mono font-bold text-white text-sm">{h.ticker}</td>
                    <td className="px-5 py-3 text-gray-400 text-right text-xs">{h.quantity.toFixed(4)}</td>
                    <td className="px-5 py-3 text-gray-400 text-right text-xs">${h.current_price?.toFixed(2) ?? '—'}</td>
                    <td className={`px-5 py-3 text-right text-xs font-semibold ${h.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {h.unrealized_pnl >= 0 ? '+' : ''}${h.unrealized_pnl.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Live news feed (MOD6) */}
      {news.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-800">
            <h3 className="text-sm font-semibold text-gray-300">İzleme Listesi Haberleri</h3>
          </div>
          <div className="divide-y divide-gray-800">
            {news.map((item, i) => (
              <div key={i} className="px-5 py-3 hover:bg-gray-800/40 transition-colors">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-mono font-bold text-violet-400">{item.ticker}</span>
                      <span className="text-xs text-gray-600">{item.source}</span>
                      <span className="text-xs text-gray-700">{new Date(item.published_at).toLocaleDateString('tr-TR')}</span>
                    </div>
                    <p className="text-sm text-gray-300 line-clamp-2">{item.title}</p>
                  </div>
                  <a href={item.url} target="_blank" rel="noreferrer" className="text-gray-600 hover:text-violet-400 transition-colors shrink-0 mt-0.5">
                    <ExternalLink size={13} />
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function KpiCard({ icon, label, value, sub, color = 'text-white', accent = 'from-violet-500/5' }: {
  icon: React.ReactNode; label: string; value: string; sub?: string; color?: string; accent?: string
}) {
  return (
    <div className={`bg-gradient-to-br ${accent} to-gray-900 border border-gray-800 rounded-2xl p-5`}>
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-xl bg-gray-800 text-violet-400 shrink-0">{icon}</div>
        <div>
          <p className="text-gray-500 text-xs font-medium uppercase tracking-wider mb-1">{label}</p>
          <p className={`text-xl font-bold ${color} leading-none`}>{value}</p>
          {sub && <p className={`text-xs mt-1 ${color} opacity-70`}>{sub}</p>}
        </div>
      </div>
    </div>
  )
}
