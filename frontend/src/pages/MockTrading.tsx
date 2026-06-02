import { useEffect, useState, useCallback } from 'react'
import axios from 'axios'
import {
  TrendingUp, TrendingDown, DollarSign, ShoppingCart, BarChart2,
  RefreshCw, RotateCcw, AlertCircle, CheckCircle, Loader2
} from 'lucide-react'

interface Holding {
  ticker: string
  quantity: number
  avg_buy_price: number
  current_price: number
  market_value: number
  unrealized_pnl: number
  pnl_pct: number
}

interface PortfolioData {
  id: number
  initial_capital: number
  cash_available: number
  positions_value: number
  total_value: number
  total_pnl: number
  total_pnl_pct: number
  holdings: Holding[]
  benchmark_ticker?: string
  benchmark_return_pct?: number | null
  alpha_pct?: number | null
}

interface OrderResult {
  order_id: number
  ticker: string
  action: string
  quantity: number
  price: number
  total_value: number
  commission: number
  status: string
}

function StatCard({
  icon, label, value, sub, positive,
}: {
  icon: React.ReactNode
  label: string
  value: string
  sub?: string
  positive?: boolean
}) {
  const valueColor =
    positive === undefined ? 'text-white' : positive ? 'text-emerald-400' : 'text-red-400'
  const accent =
    positive === undefined ? 'from-violet-500/5' : positive ? 'from-emerald-500/10' : 'from-red-500/10'
  return (
    <div className={`bg-gradient-to-br ${accent} to-gray-900 border border-gray-800 rounded-2xl p-4 flex items-start gap-3`}>
      <div className="p-2 rounded-xl bg-gray-800 text-violet-400 shrink-0">{icon}</div>
      <div>
        <p className="text-gray-500 text-xs font-medium uppercase tracking-wider mb-1">{label}</p>
        <p className={`text-xl font-bold leading-none ${valueColor}`}>{value}</p>
        {sub && <p className={`text-xs mt-1 ${valueColor} opacity-70`}>{sub}</p>}
      </div>
    </div>
  )
}

export default function MockTrading() {
  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [fetchError, setFetchError] = useState(false)

  // Order form
  const [ticker, setTicker] = useState('')
  const [action, setAction] = useState<'BUY' | 'SELL'>('BUY')
  const [quantity, setQuantity] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [orderResult, setOrderResult] = useState<{ ok: boolean; msg: string } | null>(null)

  // Reset
  const [resetting, setResetting] = useState(false)

  const fetchPortfolio = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    else setRefreshing(true)
    try {
      // Use /performance to get benchmark data alongside portfolio
      const { data } = await axios.get<PortfolioData>('/api/trading/performance')
      setPortfolio(data)
      setFetchError(false)
    } catch {
      setFetchError(true)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { fetchPortfolio() }, [fetchPortfolio])

  const handleOrder = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!ticker.trim() || !quantity || parseFloat(quantity) <= 0) return
    setSubmitting(true)
    setOrderResult(null)
    try {
      const { data } = await axios.post<OrderResult>('/api/trading/order', {
        ticker: ticker.toUpperCase(),
        action,
        quantity: parseFloat(quantity),
      })
      setOrderResult({
        ok: true,
        msg: `✓ ${data.action} ${data.quantity} ${data.ticker} @ $${data.price.toFixed(2)} — Toplam: $${data.total_value.toFixed(2)}`,
      })
      setTicker('')
      setQuantity('')
      await fetchPortfolio(true)
    } catch (err: any) {
      setOrderResult({
        ok: false,
        msg: err.response?.data?.detail || 'Emir gönderilemedi.',
      })
    } finally {
      setSubmitting(false)
    }
  }

  const handleReset = async () => {
    if (!confirm('Portföyü sıfırlamak istediğinizden emin misiniz? Tüm pozisyonlar silinecek.')) return
    setResetting(true)
    try {
      await axios.post('/api/trading/reset', { initial_capital: 100000 })
      await fetchPortfolio()
    } catch {
      // ignore
    } finally {
      setResetting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        <Loader2 className="animate-spin mr-2" size={20} /> Yükleniyor...
      </div>
    )
  }

  if (fetchError || !portfolio) {
    return (
      <div className="p-6 space-y-4">
        <h2 className="text-xl font-bold text-white tracking-tight">Simülasyon Trading</h2>
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 flex flex-col items-center gap-3 text-center">
          <AlertCircle size={32} className="text-red-400" />
          <p className="text-slate-300">Portföy yüklenemedi. Sunucu bağlantısını kontrol edin.</p>
          <button
            onClick={() => fetchPortfolio()}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm transition"
          >
            Tekrar Dene
          </button>
        </div>
      </div>
    )
  }

  const p = portfolio
  const pnlPositive = p.total_pnl >= 0
  const alphaPositive = (p.alpha_pct ?? 0) >= 0

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white tracking-tight">Simülasyon Trading</h2>
        <div className="flex gap-2">
          <button
            onClick={() => fetchPortfolio(true)}
            disabled={refreshing}
            className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-gray-800 border border-gray-700 text-gray-300 hover:bg-gray-700 text-sm transition disabled:opacity-50"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            Güncelle
          </button>
          <button
            onClick={handleReset}
            disabled={resetting}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-red-900/40 text-red-400 hover:bg-red-900/60 text-sm transition disabled:opacity-50"
          >
            <RotateCcw size={14} className={resetting ? 'animate-spin' : ''} />
            Sıfırla
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={<DollarSign size={20} />}
          label="Toplam Değer"
          value={`$${p.total_value.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}`}
        />
        <StatCard
          icon={pnlPositive ? <TrendingUp size={20} /> : <TrendingDown size={20} />}
          label="Toplam K/Z"
          value={`${pnlPositive ? '+' : ''}$${p.total_pnl.toFixed(2)}`}
          sub={`${pnlPositive ? '+' : ''}${p.total_pnl_pct.toFixed(2)}%`}
          positive={pnlPositive}
        />
        <StatCard
          icon={<DollarSign size={20} />}
          label="Nakit"
          value={`$${p.cash_available.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}`}
        />
        <StatCard
          icon={<BarChart2 size={20} />}
          label={`Alpha vs ${p.benchmark_ticker || 'SPY'}`}
          value={
            p.alpha_pct !== null && p.alpha_pct !== undefined
              ? `${alphaPositive ? '+' : ''}${p.alpha_pct.toFixed(2)}%`
              : '—'
          }
          sub={
            p.benchmark_return_pct !== null && p.benchmark_return_pct !== undefined
              ? `${p.benchmark_ticker || 'SPY'}: ${p.benchmark_return_pct >= 0 ? '+' : ''}${p.benchmark_return_pct.toFixed(2)}%`
              : undefined
          }
          positive={p.alpha_pct !== null && p.alpha_pct !== undefined ? alphaPositive : undefined}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Order Form */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <ShoppingCart size={18} className="text-indigo-400" /> Emir Ver
          </h3>
          <form onSubmit={handleOrder} className="space-y-3">
            {/* Action tabs */}
            <div className="flex rounded-xl overflow-hidden border border-gray-700">
              <button
                type="button"
                onClick={() => setAction('BUY')}
                className={`flex-1 py-2 text-sm font-medium transition ${
                  action === 'BUY'
                    ? 'bg-emerald-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:text-white'
                }`}
              >
                Al
              </button>
              <button
                type="button"
                onClick={() => setAction('SELL')}
                className={`flex-1 py-2 text-sm font-medium transition ${
                  action === 'SELL'
                    ? 'bg-red-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:text-white'
                }`}
              >
                Sat
              </button>
            </div>

            <input
              type="text"
              placeholder="Sembol (örn. AAPL)"
              value={ticker}
              onChange={e => setTicker(e.target.value.toUpperCase())}
              className="w-full bg-gray-800 border border-gray-700 rounded-xl px-3 py-2 text-white text-sm placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent transition"
              required
            />
            <input
              type="number"
              placeholder="Adet"
              value={quantity}
              onChange={e => setQuantity(e.target.value)}
              min="0.0001"
              step="any"
              className="w-full bg-gray-800 border border-gray-700 rounded-xl px-3 py-2 text-white text-sm placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent transition"
              required
            />

            <button
              type="submit"
              disabled={submitting}
              className={`w-full py-2.5 rounded-xl text-white text-sm font-semibold transition disabled:opacity-50 flex items-center justify-center gap-2 shadow-lg ${
                action === 'BUY' ? 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-500/20' : 'bg-red-600 hover:bg-red-500 shadow-red-500/20'
              }`}
            >
              {submitting ? (
                <><Loader2 size={14} className="animate-spin" /> İşleniyor...</>
              ) : (
                `${action === 'BUY' ? 'Al' : 'Sat'} Emri Ver`
              )}
            </button>

            {orderResult && (
              <div
                className={`flex items-start gap-2 rounded-lg px-3 py-2 text-xs ${
                  orderResult.ok
                    ? 'bg-emerald-900/40 text-emerald-400'
                    : 'bg-red-900/40 text-red-400'
                }`}
              >
                {orderResult.ok
                  ? <CheckCircle size={14} className="mt-0.5 shrink-0" />
                  : <AlertCircle size={14} className="mt-0.5 shrink-0" />}
                {orderResult.msg}
              </div>
            )}
          </form>
        </div>

        {/* Holdings */}
        <div className="lg:col-span-2 bg-gray-900 border border-gray-800 rounded-2xl p-5">
          <h3 className="text-lg font-semibold text-white mb-4">Açık Pozisyonlar</h3>
          {p.holdings.length === 0 ? (
            <p className="text-slate-500 text-sm">Henüz pozisyon yok.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-400 text-left text-xs">
                    <th className="pb-2">Sembol</th>
                    <th className="pb-2 text-right">Adet</th>
                    <th className="pb-2 text-right">Ort. Maliyet</th>
                    <th className="pb-2 text-right">Güncel Fiyat</th>
                    <th className="pb-2 text-right">Piyasa Değeri</th>
                    <th className="pb-2 text-right">K/Z</th>
                    <th className="pb-2 text-right">K/Z %</th>
                  </tr>
                </thead>
                <tbody>
                  {p.holdings.map(h => (
                    <tr key={h.ticker} className="border-t border-gray-800">
                      <td className="py-2 font-mono font-bold text-white">{h.ticker}</td>
                      <td className="py-2 text-right text-slate-300">{h.quantity.toFixed(4)}</td>
                      <td className="py-2 text-right text-slate-300">${h.avg_buy_price.toFixed(2)}</td>
                      <td className="py-2 text-right text-slate-300">${h.current_price.toFixed(2)}</td>
                      <td className="py-2 text-right text-slate-300">${h.market_value.toFixed(2)}</td>
                      <td className={`py-2 text-right font-semibold ${h.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {h.unrealized_pnl >= 0 ? '+' : ''}${h.unrealized_pnl.toFixed(2)}
                      </td>
                      <td className={`py-2 text-right font-semibold ${h.pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {h.pnl_pct >= 0 ? '+' : ''}{h.pnl_pct.toFixed(2)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
