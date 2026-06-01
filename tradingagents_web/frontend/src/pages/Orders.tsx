import { useEffect, useState } from 'react'
import axios from 'axios'

interface Order {
  id: number
  mode: string
  ticker: string
  action: string
  quantity_requested: number
  quantity_filled: number
  status: string
  price_per_share: number | null
  total_value: number | null
  ai_signal: string
  created_at: string
}

const STATUS_COLORS: Record<string, string> = {
  FILLED: 'text-emerald-400',
  REJECTED: 'text-red-400',
  PARTIALLY_FILLED: 'text-yellow-400',
  PENDING: 'text-slate-400',
}

const ACTION_COLORS: Record<string, string> = {
  BUY: 'text-emerald-400',
  SELL: 'text-red-400',
}

export default function Orders() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [mode, setMode] = useState<string>('')

  const fetch = () => {
    const params = mode ? `?mode=${mode}` : ''
    axios.get(`/api/portfolio/orders${params}`).then(r => { setOrders(r.data); setLoading(false) })
  }

  useEffect(() => { fetch() }, [mode])

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Emir Geçmişi</h2>
        <select className="bg-slate-700 text-white rounded-lg px-3 py-1.5 text-sm outline-none" value={mode} onChange={e => setMode(e.target.value)}>
          <option value="">Tümü</option>
          <option value="simulation">Simülasyon</option>
          <option value="live">Canlı</option>
        </select>
      </div>

      {loading ? <p className="text-slate-400">Yükleniyor...</p> : (
        orders.length === 0 ? <p className="text-slate-500">Henüz emir yok.</p> : (
          <div className="bg-slate-800 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-700">
                <tr className="text-slate-300 text-left">
                  <th className="px-4 py-3">Sembol</th>
                  <th className="px-4 py-3">Yön</th>
                  <th className="px-4 py-3">Miktar</th>
                  <th className="px-4 py-3">Fiyat</th>
                  <th className="px-4 py-3">Toplam</th>
                  <th className="px-4 py-3">Durum</th>
                  <th className="px-4 py-3">Sinyal</th>
                  <th className="px-4 py-3">Mod</th>
                  <th className="px-4 py-3">Tarih</th>
                </tr>
              </thead>
              <tbody>
                {orders.map(o => (
                  <tr key={o.id} className="border-t border-slate-700 hover:bg-slate-750">
                    <td className="px-4 py-2 font-mono font-bold text-white">{o.ticker}</td>
                    <td className={`px-4 py-2 font-semibold ${ACTION_COLORS[o.action] || 'text-white'}`}>{o.action}</td>
                    <td className="px-4 py-2 text-slate-300">{o.quantity_filled.toFixed(4)}</td>
                    <td className="px-4 py-2 text-slate-300">{o.price_per_share ? `$${o.price_per_share.toFixed(2)}` : '—'}</td>
                    <td className="px-4 py-2 text-slate-300">{o.total_value ? `$${o.total_value.toFixed(2)}` : '—'}</td>
                    <td className={`px-4 py-2 font-semibold ${STATUS_COLORS[o.status] || 'text-slate-300'}`}>{o.status}</td>
                    <td className="px-4 py-2 text-slate-400 text-xs">{o.ai_signal}</td>
                    <td className="px-4 py-2 text-slate-500 text-xs">{o.mode}</td>
                    <td className="px-4 py-2 text-slate-500 text-xs">{new Date(o.created_at).toLocaleString('tr-TR')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}
