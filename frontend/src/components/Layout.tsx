import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import {
  LayoutDashboard, Search, BookMarked, Briefcase,
  Settings, ScrollText, TrendingUp, LogOut, Clock,
  FlaskConical, PieChart, Loader2, ChevronRight,
  AlertCircle, AlertTriangle, CheckCircle, Info, X,
  BarChart2, Bell,
} from 'lucide-react'
import { useEffect, useState, useCallback } from 'react'
import axios from 'axios'
import type { Notification } from '../utils/notify'
import UpdateBanner from './UpdateBanner'

interface RunningTask { ticker: string; taskId: string; startedAt: string }

const NAV = [
  { to: '/dashboard',  label: 'Dashboard',       icon: LayoutDashboard },
  { to: '/analysis',   label: 'Analiz',           icon: Search },
  { to: '/chart',      label: 'Grafik',           icon: TrendingUp },
  { to: '/trading',    label: 'Simülasyon',        icon: FlaskConical },
  { to: '/portfolio',  label: 'Portföy',           icon: PieChart },
  { to: '/watchlist',  label: 'İzleme Listesi',    icon: BookMarked },
  { to: '/orders',     label: 'Emirler',           icon: Briefcase },
  { to: '/performance', label: 'Performans',         icon: BarChart2 },
  { to: '/alerts',     label: 'Alarmlar',           icon: Bell },
  { to: '/settings',   label: 'Ayarlar',           icon: Settings },
  { to: '/logs',       label: 'Loglar',            icon: ScrollText },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [cronStatus, setCronStatus] = useState<{ next_run_time: string | null }>({ next_run_time: null })
  const [runningTask, setRunningTask] = useState<RunningTask | null>(() => {
    try { return JSON.parse(localStorage.getItem('ta_task_running') || 'null') } catch { return null }
  })

  // Poll cron status
  useEffect(() => {
    const fetch = () => axios.get('/api/cron/status').then(r => setCronStatus(r.data)).catch(() => {})
    fetch()
    const id = setInterval(fetch, 30_000)
    return () => clearInterval(id)
  }, [])

  // Listen for analysis start/stop events from Analysis.tsx
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === 'ta_task_running') {
        try { setRunningTask(e.newValue ? JSON.parse(e.newValue) : null) }
        catch { setRunningTask(null) }
      }
    }
    window.addEventListener('storage', onStorage)
    // Also poll localStorage directly (same-tab changes don't fire storage event)
    const id = setInterval(() => {
      try {
        const raw = localStorage.getItem('ta_task_running')
        const val: RunningTask | null = raw ? JSON.parse(raw) : null
        setRunningTask(prev => {
          const prevJson = JSON.stringify(prev)
          const nextJson = JSON.stringify(val)
          return prevJson === nextJson ? prev : val
        })
      } catch { /* ignore */ }
    }, 1000)
    return () => { window.removeEventListener('storage', onStorage); clearInterval(id) }
  }, [])

  const handleLogout = () => { logout(); navigate('/login') }

  // ── Global notification toast stack ────────────────────────────────────────
  const [toasts, setToasts] = useState<Notification[]>([])

  const dismiss = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  useEffect(() => {
    const handler = (e: Event) => {
      const n = (e as CustomEvent<Notification>).detail
      setToasts(prev => [...prev.slice(-4), n]) // keep max 5
      // Auto-dismiss after 6s (errors) or 4s (others)
      const ms = n.type === 'error' ? 6000 : 4000
      setTimeout(() => dismiss(n.id), ms)
    }
    window.addEventListener('ta-notify', handler)
    return () => window.removeEventListener('ta-notify', handler)
  }, [dismiss])
  // ──────────────────────────────────────────────────────────────────────────

  return (
    <div className="flex min-h-screen bg-gray-950">
      {/* ── Sidebar ── */}
      <aside className="w-60 bg-gray-900 border-r border-gray-800 flex flex-col shrink-0">

        {/* Logo */}
        <div className="px-5 py-5 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-500/20">
              <TrendingUp size={15} className="text-white" strokeWidth={2.5} />
            </div>
            <div>
              <p className="text-white font-bold text-sm tracking-tight leading-none">TradingAgents</p>
              <p className="text-gray-500 text-xs mt-0.5">AI Portfolio</p>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-3 space-y-0.5 overflow-y-auto">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 group ` +
                (isActive
                  ? 'bg-violet-500/10 text-violet-300 border border-violet-500/20 shadow-sm'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800')
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={16} className={isActive ? 'text-violet-400' : 'text-gray-500 group-hover:text-gray-300'} />
                  <span className="flex-1">{label}</span>
                  {isActive && <ChevronRight size={12} className="text-violet-500 opacity-60" />}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Running analysis indicator */}
        {runningTask && (
          <div className="mx-3 mb-2 px-3 py-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
            <div className="flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </span>
              <Loader2 size={12} className="text-emerald-400 animate-spin" />
              <div className="flex-1 min-w-0">
                <p className="text-emerald-300 text-xs font-semibold truncate">{runningTask.ticker} analiz ediliyor</p>
                <p className="text-emerald-600 text-xs">Arka planda çalışıyor...</p>
              </div>
            </div>
          </div>
        )}

        {/* Cron status */}
        {cronStatus.next_run_time && (
          <div className="mx-3 mb-2 px-3 py-2 rounded-xl bg-gray-800/50">
            <div className="flex items-center gap-1.5 text-xs text-gray-500">
              <Clock size={11} />
              <span>Sonraki: {new Date(cronStatus.next_run_time).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}</span>
            </div>
          </div>
        )}

        {/* User */}
        <div className="px-3 py-3 border-t border-gray-800">
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-gray-800 transition-colors group cursor-default">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-700 flex items-center justify-center text-white text-xs font-bold shrink-0">
              {user?.charAt(0).toUpperCase() || 'U'}
            </div>
            <span className="text-gray-300 text-sm font-medium flex-1 truncate">{user}</span>
            <button
              onClick={handleLogout}
              className="text-gray-600 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
              title="Çıkış"
            >
              <LogOut size={14} />
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main ── */}
      <main className="flex-1 overflow-y-auto min-h-screen bg-gray-950">
        <UpdateBanner />
        {children}
      </main>

      {/* ── Toast notifications ── */}
      {toasts.length > 0 && (
        <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 w-96 max-w-[calc(100vw-2rem)]">
          {toasts.map(t => <Toast key={t.id} n={t} onDismiss={dismiss} />)}
        </div>
      )}
    </div>
  )
}

// ── Toast component ───────────────────────────────────────────────────────────
const TOAST_STYLES = {
  error:   { bar: 'bg-red-500',    bg: 'bg-gray-900 border-red-500/30',    icon: AlertCircle,   text: 'text-red-400'    },
  warning: { bar: 'bg-yellow-500', bg: 'bg-gray-900 border-yellow-500/30', icon: AlertTriangle, text: 'text-yellow-400' },
  success: { bar: 'bg-emerald-500',bg: 'bg-gray-900 border-emerald-500/30',icon: CheckCircle,   text: 'text-emerald-400'},
  info:    { bar: 'bg-blue-500',   bg: 'bg-gray-900 border-blue-500/30',   icon: Info,          text: 'text-blue-400'   },
}

function Toast({ n, onDismiss }: { n: Notification; onDismiss: (id: string) => void }) {
  const s = TOAST_STYLES[n.type]
  const Icon = s.icon
  return (
    <div className={`relative overflow-hidden rounded-2xl border shadow-xl shadow-black/40 ${s.bg} animate-in slide-in-from-right-4 duration-300`}>
      {/* Coloured left bar */}
      <div className={`absolute left-0 top-0 bottom-0 w-1 ${s.bar}`} />
      <div className="flex items-start gap-3 px-4 py-3 pl-5">
        <Icon size={17} className={`${s.text} shrink-0 mt-0.5`} />
        <div className="flex-1 min-w-0">
          {n.title && <p className={`text-xs font-semibold mb-0.5 ${s.text}`}>{n.title}</p>}
          <p className="text-gray-300 text-sm leading-snug break-words">{n.message}</p>
        </div>
        <button
          onClick={() => onDismiss(n.id)}
          className="text-gray-600 hover:text-gray-400 transition-colors shrink-0 mt-0.5"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  )
}
