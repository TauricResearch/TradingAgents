import { useEffect, useState } from 'react'
import axios from 'axios'
import { Bell, BellOff, Plus, Trash2, RefreshCw } from 'lucide-react'

interface Alert {
  id: number; ticker: string; condition: 'above' | 'below'
  target_price: number; auto_analyze: boolean; enabled: boolean
  triggered_at: string | null; created_at: string
}

const Input = "bg-gray-800 border border-gray-700 text-white rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-violet-500 transition w-full"

export default function Alerts() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [ticker, setTicker] = useState('')
  const [condition, setCondition] = useState<'above' | 'below'>('above')
  const [targetPrice, setTargetPrice] = useState('')
  const [autoAnalyze, setAutoAnalyze] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      const { data } = await axios.get('/api/alerts')
      setAlerts(data)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async () => {
    const t = ticker.trim().toUpperCase()
    const price = parseFloat(targetPrice)
    if (!t || isNaN(price) || price <= 0) { setError('Geçerli bir sembol ve fiyat girin.'); return }
    setSaving(true); setError(null)
    try {
      await axios.post('/api/alerts', { ticker: t, condition, target_price: price, auto_analyze: autoAnalyze })
      setTicker(''); setTargetPrice(''); setAutoAnalyze(false)
      await load()
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Alarm oluşturulamadı.')
    } finally { setSaving(false) }
  }

  const toggleEnabled = async (a: Alert) => {
    await axios.patch(`/api/alerts/${a.id}`, { enabled: !a.enabled })
    setAlerts(prev => prev.map(x => x.id === a.id ? { ...x, enabled: !x.enabled } : x))
  }

  const deleteAlert = async (id: number) => {
    await axios.delete(`/api/alerts/${id}`)
    setAlerts(prev => prev.filter(x => x.id !== id))
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-3xl">
      <h2 className="text-lg md:text-xl font-bold text-white tracking-tight">Fiyat Alarmları</h2>

      {/* Create form */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 md:p-5 space-y-4">
        <h3 className="text-sm font-semibold text-violet-400 uppercase tracking-wider">Yeni Alarm</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-gray-500 mb-1.5 block uppercase tracking-wider">Sembol</label>
            <input className={Input} placeholder="AAPL" value={ticker} onChange={e => setTicker(e.target.value.toUpperCase())} />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1.5 block uppercase tracking-wider">Koşul</label>
            <select className={Input} value={condition} onChange={e => setCondition(e.target.value as any)}>
              <option value="above">Üstüne çıkınca</option>
              <option value="below">Altına inince</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1.5 block uppercase tracking-wider">Hedef Fiyat ($)</label>
            <input className={Input} type="number" step="0.01" placeholder="150.00" value={targetPrice} onChange={e => setTargetPrice(e.target.value)} />
          </div>
          <div className="flex flex-col justify-end pb-1">
            <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
              <input type="checkbox" checked={autoAnalyze} onChange={e => setAutoAnalyze(e.target.checked)} className="w-4 h-4 accent-violet-600" />
              Otomatik analiz başlat
            </label>
          </div>
        </div>
        {error && <p className="text-red-400 text-sm">{error}</p>}
        <button onClick={handleCreate} disabled={saving}
          className="flex items-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm font-semibold px-4 py-2 rounded-xl transition">
          {saving ? <RefreshCw size={14} className="animate-spin" /> : <Plus size={14} />} Alarm Ekle
        </button>
      </div>

      {/* Alert list */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
        <div className="px-4 md:px-5 py-3 md:py-4 border-b border-gray-800">
          <h3 className="text-sm font-semibold text-gray-300">Aktif Alarmlar ({alerts.filter(a => a.enabled && !a.triggered_at).length})</h3>
        </div>
        {loading ? <div className="p-8 text-gray-500 text-sm text-center">Yükleniyor...</div>
          : alerts.length === 0 ? <div className="p-8 text-gray-600 text-sm text-center">Henüz alarm yok.</div>
          : (
            <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[480px]">
              <thead>
                <tr className="text-gray-600 text-xs uppercase tracking-wider bg-gray-800/30">
                  <th className="px-4 py-3 text-left">Sembol</th>
                  <th className="px-4 py-3 text-left hidden sm:table-cell">Koşul</th>
                  <th className="px-4 py-3 text-right">Hedef</th>
                  <th className="px-4 py-3 text-center hidden sm:table-cell">Otom.</th>
                  <th className="px-4 py-3 text-center">Durum</th>
                  <th className="px-4 py-3 text-center">İşlem</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map(a => (
                  <tr key={a.id} className={`border-t border-gray-800 transition-colors ${a.triggered_at ? 'opacity-50' : ''}`}>
                    <td className="px-4 py-3 font-mono font-bold text-white">{a.ticker}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs hidden sm:table-cell">
                      {a.condition === 'above' ? '↑ Üstüne çıkınca' : '↓ Altına inince'}
                    </td>
                    <td className="px-4 py-3 text-right text-white font-mono text-xs">${a.target_price.toFixed(2)}</td>
                    <td className="px-4 py-3 text-center text-xs hidden sm:table-cell">
                      {a.auto_analyze ? <span className="text-violet-400">✓</span> : <span className="text-gray-600">—</span>}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {a.triggered_at
                        ? <span className="text-xs text-yellow-500">Tetiklendi</span>
                        : a.enabled
                          ? <span className="text-xs text-emerald-400">Aktif</span>
                          : <span className="text-xs text-gray-600">Pasif</span>
                      }
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className="flex items-center justify-center gap-2">
                        <button onClick={() => toggleEnabled(a)} className="text-gray-500 hover:text-white transition-colors" title={a.enabled ? 'Pasifleştir' : 'Aktifleştir'}>
                          {a.enabled ? <Bell size={14} /> : <BellOff size={14} />}
                        </button>
                        <button onClick={() => deleteAlert(a.id)} className="text-gray-500 hover:text-red-400 transition-colors">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
      </div>
    </div>
  )
}
