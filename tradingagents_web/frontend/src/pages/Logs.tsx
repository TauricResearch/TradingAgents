import { useEffect, useState } from 'react'
import axios from 'axios'
import { RefreshCw } from 'lucide-react'

interface Log {
  id: number
  level: string
  source: string
  message: string
  details: string | null
  created_at: string
}

const LEVEL_COLORS: Record<string, string> = {
  INFO: 'text-sky-400 bg-sky-900/30',
  WARNING: 'text-yellow-400 bg-yellow-900/30',
  ERROR: 'text-red-400 bg-red-900/30',
  CRITICAL: 'text-red-300 bg-red-800/40',
}

export default function Logs() {
  const [logs, setLogs] = useState<Log[]>([])
  const [level, setLevel] = useState('')
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<number | null>(null)

  const fetch = () => {
    const params = level ? `?level=${level}` : ''
    axios.get(`/api/logs${params}`).then(r => { setLogs(r.data); setLoading(false) })
  }

  useEffect(() => { fetch() }, [level])

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Sistem Logları</h2>
        <div className="flex gap-3 items-center">
          <select className="bg-slate-700 text-white rounded-lg px-3 py-1.5 text-sm outline-none" value={level} onChange={e => setLevel(e.target.value)}>
            <option value="">Tüm Seviyeler</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
          <button onClick={fetch} className="text-slate-400 hover:text-white"><RefreshCw size={18} /></button>
        </div>
      </div>

      {loading ? <p className="text-slate-400">Yükleniyor...</p> : (
        logs.length === 0 ? <p className="text-slate-500">Log yok.</p> : (
          <div className="space-y-1">
            {logs.map(l => (
              <div
                key={l.id}
                className="bg-slate-800 rounded-lg px-4 py-2 cursor-pointer"
                onClick={() => setExpanded(expanded === l.id ? null : l.id)}
              >
                <div className="flex items-start gap-3 text-sm">
                  <span className={`text-xs font-bold px-2 py-0.5 rounded ${LEVEL_COLORS[l.level] || 'text-slate-400'}`}>
                    {l.level}
                  </span>
                  <span className="text-slate-400 text-xs whitespace-nowrap">
                    {new Date(l.created_at).toLocaleString('tr-TR')}
                  </span>
                  <span className="text-indigo-300 text-xs">[{l.source}]</span>
                  <span className="text-slate-300 flex-1">{l.message}</span>
                </div>
                {expanded === l.id && l.details && (
                  <pre className="mt-2 text-xs text-slate-400 bg-slate-900 rounded p-2 whitespace-pre-wrap overflow-x-auto">
                    {l.details}
                  </pre>
                )}
              </div>
            ))}
          </div>
        )
      )}
    </div>
  )
}
