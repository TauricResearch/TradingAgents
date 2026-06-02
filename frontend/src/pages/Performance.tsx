import { useEffect, useState } from 'react'
import axios from 'axios'
import { BarChart2, TrendingUp, TrendingDown, Target } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

interface PerfData {
  total: number
  win_rate: number | null
  avg_raw_return: number | null
  avg_alpha_return: number | null
  by_signal: Record<string, { count: number; wins: number; win_rate: number; avg_return: number }>
}

interface HistoryItem {
  id: number; ticker: string; trade_date: string; signal: string | null
  raw_return: number | null; alpha_return: number | null; holding_days: number | null
  duration_seconds: number; created_at: string
}

function ReturnCell({ value }: { value: number | null }) {
  if (value === null) return <span className="text-gray-600">—</span>
  const pct = (value * 100).toFixed(2)
  return <span className={value >= 0 ? 'text-emerald-400' : 'text-red-400'}>{value >= 0 ? '+' : ''}{pct}%</span>
}

export default function Performance() {
  const [perf, setPerf] = useState<PerfData | null>(null)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [ticker, setTicker] = useState('')
  const [filterTicker, setFilterTicker] = useState('')
  const [loading, setLoading] = useState(true)

  const load = async (t?: string) => {
    setLoading(true)
    try {
      const [p, h] = await Promise.all([
        axios.get('/api/analysis/performance', { params: t ? { ticker: t } : {} }).then(r => r.data),
        axios.get('/api/analysis/history', { params: { limit: 100, ...(t ? { ticker: t } : {}) } }).then(r => r.data),
      ])
      setPerf(p)
      setHistory(h.filter((x: HistoryItem) => x.raw_return !== null))
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const handleFilter = () => { setFilterTicker(ticker); load(ticker || undefined) }

  const bySignalData = perf ? Object.entries(perf.by_signal).map(([sig, d]) => ({
    signal: sig, win_rate: d.win_rate, avg_return: d.avg_return, count: d.count,
  })) : []

  return (
    <div className="p-6 space-y-6 max-w-6xl">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white tracking-tight">Sinyal Performansı</h2>
        <div className="flex items-center gap-2">
          <input className="bg-gray-800 border border-gray-700 text-white rounded-xl px-3 py-1.5 text-sm w-24 uppercase font-mono outline-none focus:ring-2 focus:ring-violet-500"
            placeholder="AAPL" value={ticker} onChange={e => setTicker(e.target.value.toUpperCase())} onKeyDown={e => e.key === 'Enter' && handleFilter()} />
          <button onClick={handleFilter} className="bg-violet-600 hover:bg-violet-500 text-white text-sm px-3 py-1.5 rounded-xl transition">Filtrele</button>
          {filterTicker && <button onClick={() => { setTicker(''); setFilterTicker(''); load() }} className="text-gray-500 hover:text-white text-xs">Temizle</button>}
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-4 gap-4">{[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-gray-800 rounded-2xl animate-pulse" />)}</div>
      ) : perf && perf.total > 0 ? (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard icon={<BarChart2 size={18} />} label="Toplam Analiz" value={String(perf.total)} />
            <StatCard icon={<Target size={18} />} label="Kazanma Oranı"
              value={perf.win_rate !== null ? `${perf.win_rate}%` : '—'}
              color={perf.win_rate !== null && perf.win_rate >= 50 ? 'text-emerald-400' : 'text-red-400'} />
            <StatCard icon={<TrendingUp size={18} />} label="Ort. Ham Getiri"
              value={perf.avg_raw_return !== null ? `${perf.avg_raw_return >= 0 ? '+' : ''}${perf.avg_raw_return}%` : '—'}
              color={perf.avg_raw_return !== null && perf.avg_raw_return >= 0 ? 'text-emerald-400' : 'text-red-400'} />
            <StatCard icon={<TrendingDown size={18} />} label="Ort. Alpha"
              value={perf.avg_alpha_return !== null ? `${perf.avg_alpha_return >= 0 ? '+' : ''}${perf.avg_alpha_return}%` : '—'}
              color={perf.avg_alpha_return !== null && perf.avg_alpha_return >= 0 ? 'text-emerald-400' : 'text-red-400'} />
          </div>

          {/* Charts */}
          {bySignalData.length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5">
                <h3 className="text-sm font-semibold text-gray-300 mb-4">Sinyal Bazında Win Rate (%)</h3>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={bySignalData}>
                    <XAxis dataKey="signal" stroke="#6b7280" tick={{ fontSize: 12 }} />
                    <YAxis stroke="#6b7280" tick={{ fontSize: 11 }} domain={[0, 100]} />
                    <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }} labelStyle={{ color: '#fff' }} />
                    <Bar dataKey="win_rate" radius={[4, 4, 0, 0]}>
                      {bySignalData.map(d => (
                        <Cell key={d.signal} fill={d.win_rate >= 50 ? '#10b981' : '#ef4444'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5">
                <h3 className="text-sm font-semibold text-gray-300 mb-4">Sinyal Bazında Ort. Getiri (%)</h3>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={bySignalData}>
                    <XAxis dataKey="signal" stroke="#6b7280" tick={{ fontSize: 12 }} />
                    <YAxis stroke="#6b7280" tick={{ fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }} labelStyle={{ color: '#fff' }} />
                    <Bar dataKey="avg_return" radius={[4, 4, 0, 0]}>
                      {bySignalData.map(d => (
                        <Cell key={d.signal} fill={d.avg_return >= 0 ? '#10b981' : '#ef4444'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* History table with returns */}
          {history.length > 0 && (
            <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
              <div className="px-5 py-4 border-b border-gray-800">
                <h3 className="text-sm font-semibold text-gray-300">Geçmiş Sinyaller ve Gerçekleşen Getiriler</h3>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-gray-600 text-xs uppercase tracking-wider bg-gray-800/30">
                    <th className="px-5 py-3 text-left">Sembol</th>
                    <th className="px-5 py-3 text-left">Tarih</th>
                    <th className="px-5 py-3 text-left">Sinyal</th>
                    <th className="px-5 py-3 text-right">Ham Getiri</th>
                    <th className="px-5 py-3 text-right">Alpha</th>
                    <th className="px-5 py-3 text-right">Gün</th>
                  </tr>
                </thead>
                <tbody>
                  {history.slice(0, 50).map(item => (
                    <tr key={item.id} className="border-t border-gray-800 hover:bg-gray-800/40 transition-colors">
                      <td className="px-5 py-3 font-mono font-bold text-white">{item.ticker}</td>
                      <td className="px-5 py-3 text-gray-400 text-xs">{item.trade_date}</td>
                      <td className="px-5 py-3">
                        <span className={`text-xs font-semibold ${
                          ['Buy','Overweight'].includes(item.signal||'') ? 'text-emerald-400' :
                          ['Sell','Underweight'].includes(item.signal||'') ? 'text-red-400' : 'text-yellow-400'
                        }`}>{item.signal ?? '—'}</span>
                      </td>
                      <td className="px-5 py-3 text-right"><ReturnCell value={item.raw_return} /></td>
                      <td className="px-5 py-3 text-right"><ReturnCell value={item.alpha_return} /></td>
                      <td className="px-5 py-3 text-right text-gray-500 text-xs">{item.holding_days ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-12 text-center">
          <BarChart2 size={36} className="mx-auto text-gray-700 mb-3" />
          <p className="text-gray-500 text-sm">Henüz gerçekleşen getiri verisi yok.</p>
          <p className="text-gray-600 text-xs mt-1">Analizler sinyal tarihinden 5 iş günü sonra otomatik güncellenir.</p>
        </div>
      )}
    </div>
  )
}

function StatCard({ icon, label, value, color = 'text-white' }: { icon: React.ReactNode; label: string; value: string; color?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 flex items-start gap-3">
      <div className="p-2 rounded-xl bg-gray-800 text-violet-400 shrink-0">{icon}</div>
      <div>
        <p className="text-gray-500 text-xs font-medium uppercase tracking-wider mb-1">{label}</p>
        <p className={`text-xl font-bold ${color} leading-none`}>{value}</p>
      </div>
    </div>
  )
}
