import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import {
  LayoutDashboard, Search, BookMarked, Briefcase,
  Settings, ScrollText, TrendingUp, LogOut, Clock
} from 'lucide-react'
import { useEffect, useState } from 'react'
import axios from 'axios'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: <LayoutDashboard size={18} /> },
  { to: '/analysis', label: 'Analiz', icon: <Search size={18} /> },
  { to: '/watchlist', label: 'İzleme Listesi', icon: <BookMarked size={18} /> },
  { to: '/orders', label: 'Emirler', icon: <Briefcase size={18} /> },
  { to: '/settings', label: 'Ayarlar', icon: <Settings size={18} /> },
  { to: '/logs', label: 'Loglar', icon: <ScrollText size={18} /> },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [cronStatus, setCronStatus] = useState<{ running: boolean; next_run_time: string | null }>({ running: false, next_run_time: null })

  useEffect(() => {
    axios.get('/api/cron/status').then(r => setCronStatus(r.data)).catch(() => {})
    const interval = setInterval(() => {
      axios.get('/api/cron/status').then(r => setCronStatus(r.data)).catch(() => {})
    }, 30_000)
    return () => clearInterval(interval)
  }, [])

  const handleLogout = () => { logout(); navigate('/login') }

  return (
    <div className="flex min-h-screen bg-slate-900">
      {/* Sidebar */}
      <aside className="w-56 bg-slate-800 border-r border-slate-700 flex flex-col">
        <div className="flex items-center gap-2 px-4 py-5 border-b border-slate-700">
          <TrendingUp className="text-indigo-400" size={22} />
          <span className="text-white font-bold text-lg">TradingAgents</span>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {NAV.map(n => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition font-medium ` +
                (isActive
                  ? 'bg-indigo-600 text-white'
                  : 'text-slate-400 hover:bg-slate-700 hover:text-white')
              }
            >
              {n.icon} {n.label}
            </NavLink>
          ))}
        </nav>

        {/* Cron status pill */}
        <div className="px-4 py-2 border-t border-slate-700">
          <div className={`flex items-center gap-2 text-xs ${cronStatus.next_run_time ? 'text-emerald-400' : 'text-slate-500'}`}>
            <Clock size={12} />
            {cronStatus.next_run_time
              ? `Sonraki: ${new Date(cronStatus.next_run_time).toLocaleTimeString('tr-TR')}`
              : 'Cron devre dışı'}
          </div>
        </div>

        <div className="px-4 py-3 border-t border-slate-700 flex items-center justify-between">
          <span className="text-slate-400 text-xs">{user}</span>
          <button onClick={handleLogout} className="text-slate-500 hover:text-red-400" title="Çıkış">
            <LogOut size={16} />
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  )
}
