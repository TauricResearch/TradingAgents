import { useEffect, useState } from 'react'
import axios from 'axios'
import { TrendingUp, TrendingDown, DollarSign, Activity } from 'lucide-react'

interface Portfolio {
  id: number
  mode: string
  broker: string
  initial_capital: number
  current_balance: number
  cash_available: number
  status: string
  holdings: { ticker: string; quantity: number; current_price: number; unrealized_pnl: number }[]
}

const COLORS: Record<string, string> = {
  Buy: 'text-emerald-400',
  Overweight: 'text-green-400',
  Hold: 'text-yellow-400',
  Underweight: 'text-orange-400',
  Sell: 'text-red-400',
}

function SignalBadge({ signal }: { signal: string | null }) {
  if (!signal) return <span className="text-slate-500">—</span>
  return <span className={`font-semibold ${COLORS[signal] || 'text-slate-300'}`}>{signal}</span>
}

export default function Dashboard() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [recentAnalysis, setRecentAnalysis] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      axios.get('/api/portfolio').then(r => r.data),
      axios.get('/api/analysis/history?limit=10').then(r => r.data),
    ]).then(([p, a]) => {
      setPortfolios(p)
      setRecentAnalysis(a)
    }).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-8 text-slate-400">Yükleniyor...</div>

  const simPortfolio = portfolios.find(p => p.mode === 'simulation') || portfolios[0]

  const pnlPct = simPortfolio
    ? ((simPortfolio.current_balance - simPortfolio.initial_capital) / simPortfolio.initial_capital * 100).toFixed(2)
    : '0.00'

  const pnlPositive = parseFloat(pnlPct) >= 0
  const totalUnrealized = simPortfolio?.holdings.reduce((s, h) => s + h.unrealized_pnl, 0) || 0

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-2xl font-bold text-white">Dashboard</h2>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card icon={<DollarSign size={20} />} label="Portföy Değeri" value={`$${simPortfolio?.current_balance.toLocaleString() || '—'}`} />
        <Card
          icon={pnlPositive ? <TrendingUp size={20} /> : <TrendingDown size={20} />}
          label="Toplam Getiri"
          value={`${pnlPositive ? '+' : ''}${pnlPct}%`}
          color={pnlPositive ? 'text-emerald-400' : 'text-red-400'}
        />
        <Card icon={<DollarSign size={20} />} label="Nakit" value={`$${simPortfolio?.cash_available.toLocaleString() || '—'}`} />
        <Card
          icon={<Activity size={20} />}
          label="Gerçekleşmemiş K/Z"
          value={`${totalUnrealized >= 0 ? '+' : ''}$${totalUnrealized.toFixed(2)}`}
          color={totalUnrealized >= 0 ? 'text-emerald-400' : 'text-red-400'}
        />
      </div>

      {/* Recent Analysis */}
      <div className="bg-slate-800 rounded-xl p-5">
        <h3 className="text-lg font-semibold text-white mb-4">Son Analizler</h3>
        {recentAnalysis.length === 0 ? (
          <p className="text-slate-400 text-sm">Henüz analiz yapılmadı.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 text-left">
                <th className="pb-2">Sembol</th>
                <th className="pb-2">Tarih</th>
                <th className="pb-2">Sinyal</th>
                <th className="pb-2">Süre</th>
                <th className="pb-2">Kaynak</th>
              </tr>
            </thead>
            <tbody>
              {recentAnalysis.map(a => (
                <tr key={a.id} className="border-t border-slate-700">
                  <td className="py-2 font-mono font-semibold text-white">{a.ticker}</td>
                  <td className="py-2 text-slate-300">{a.trade_date}</td>
                  <td className="py-2"><SignalBadge signal={a.signal} /></td>
                  <td className="py-2 text-slate-400">{a.duration_seconds?.toFixed(1)}s</td>
                  <td className="py-2 text-slate-500">{a.triggered_by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Holdings */}
      {simPortfolio?.holdings.length > 0 && (
        <div className="bg-slate-800 rounded-xl p-5">
          <h3 className="text-lg font-semibold text-white mb-4">Açık Pozisyonlar</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 text-left">
                <th className="pb-2">Sembol</th>
                <th className="pb-2">Miktar</th>
                <th className="pb-2">Güncel Fiyat</th>
                <th className="pb-2">Ger. K/Z</th>
              </tr>
            </thead>
            <tbody>
              {simPortfolio.holdings.map(h => (
                <tr key={h.ticker} className="border-t border-slate-700">
                  <td className="py-2 font-mono font-semibold text-white">{h.ticker}</td>
                  <td className="py-2 text-slate-300">{h.quantity.toFixed(4)}</td>
                  <td className="py-2 text-slate-300">${h.current_price.toFixed(2)}</td>
                  <td className={`py-2 font-semibold ${h.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {h.unrealized_pnl >= 0 ? '+' : ''}${h.unrealized_pnl.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Card({ icon, label, value, color = 'text-white' }: { icon: React.ReactNode; label: string; value: string; color?: string }) {
  return (
    <div className="bg-slate-800 rounded-xl p-4 flex items-start gap-3">
      <div className="text-indigo-400 mt-0.5">{icon}</div>
      <div>
        <p className="text-slate-400 text-xs">{label}</p>
        <p className={`text-lg font-bold ${color}`}>{value}</p>
      </div>
    </div>
  )
}
