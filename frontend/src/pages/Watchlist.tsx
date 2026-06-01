import { useEffect, useState } from 'react'
import axios from 'axios'
import { Plus, Trash2, RefreshCw } from 'lucide-react'

export default function Watchlist() {
  const [tickers, setTickers] = useState<string[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(true)

  const fetch = () => axios.get('/api/watchlist').then(r => { setTickers(r.data); setLoading(false) })
  useEffect(() => { fetch() }, [])

  const add = async () => {
    if (!input.trim()) return
    const res = await axios.post(`/api/watchlist/${input.trim().toUpperCase()}`)
    setTickers(res.data)
    setInput('')
  }

  const remove = async (t: string) => {
    const res = await axios.delete(`/api/watchlist/${t}`)
    setTickers(res.data)
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">İzleme Listesi</h2>
        <button onClick={fetch} className="text-slate-400 hover:text-white"><RefreshCw size={18} /></button>
      </div>

      {/* Add */}
      <div className="flex gap-3">
        <input
          className="bg-slate-700 text-white rounded-lg px-3 py-2 uppercase font-mono w-40 focus:ring-2 focus:ring-indigo-500 outline-none"
          placeholder="AAPL"
          value={input}
          onChange={e => setInput(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === 'Enter' && add()}
        />
        <button onClick={add} className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg px-4 py-2 font-semibold">
          <Plus size={16} /> Ekle
        </button>
      </div>

      {/* List */}
      {loading ? <p className="text-slate-400">Yükleniyor...</p> : (
        tickers.length === 0
          ? <p className="text-slate-500">İzleme listesi boş.</p>
          : <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {tickers.map(t => (
                <div key={t} className="bg-slate-800 rounded-xl flex items-center justify-between px-4 py-3">
                  <span className="font-mono font-bold text-white">{t}</span>
                  <button onClick={() => remove(t)} className="text-slate-500 hover:text-red-400 ml-3">
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
            </div>
      )}
    </div>
  )
}
