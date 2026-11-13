import { useMemo, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AccountContext } from './account'
import type { Account, Execution, Overview, Strategy } from './api'
import { accountPath } from './api'
import { LiveBanner } from './components/LiveBanner'
import { TopBar } from './components/TopBar'
import { ErrorBox, Loading } from './components/Status'
import { strategyVars } from './content/vars'
import { useFetch } from './hooks'
import { Guide } from './pages/Guide'
import { History } from './pages/History'
import { Overview as OverviewPage } from './pages/Overview'
import { Research } from './pages/Research'
import { ResearchDetail } from './pages/ResearchDetail'
import { Settings } from './pages/Settings'
import { Signals } from './pages/Signals'
import { saveAccountId, savedAccountId } from './savedAccount'
import { StrategyContext } from './strategy'

const OVERVIEW_REFRESH_MS = 60_000

interface ShellProps {
  account: Account
  accounts: Account[]
  select: (id: string) => void
}

/** Routes and layout for one account; the overview and execution feeds are shared via context. */
function Shell({ account, accounts, select }: ShellProps) {
  const overview = useFetch<Overview>(accountPath(account.id, 'overview'), OVERVIEW_REFRESH_MS)
  const execution = useFetch<Execution>(
    account.exchange ? accountPath(account.id, 'execution') : null,
    OVERVIEW_REFRESH_MS,
  )
  return (
    <AccountContext value={{ account, accounts, select, overview, execution }}>
      <TopBar />
      {/* Keyed by account: switching resets the pages' local state while the top bar, and the focus on its switch, stay. */}
      <main key={account.id} className="mx-auto max-w-[1500px] px-3 py-3">
        {account.live && <LiveBanner />}
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/research" element={<Research />} />
          <Route path="/research/:coin/:date" element={<ResearchDetail />} />
          {(account.intraday || account.exchange) && <Route path="/signals" element={<Signals />} />}
          <Route path="/history" element={<History />} />
          <Route path="/guide" element={<Guide />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </AccountContext>
  )
}

export default function App() {
  const accounts = useFetch<Account[]>('/api/accounts')
  // The strategy constants quoted by the guide and the `?` marks; placeholders show raw until loaded.
  const strategy = useFetch<Strategy>('/api/strategy')
  const vars = useMemo(() => (strategy.data ? strategyVars(strategy.data) : {}), [strategy.data])
  // The account this browser picked last time; a hook, so it sits above the early returns.
  const [chosen, setChosen] = useState<string | null>(savedAccountId)

  if (accounts.error && !accounts.data) {
    return <ErrorBox error={accounts.error} onRetry={accounts.refresh} />
  }
  if (!accounts.data) return <Loading />
  // An account without a ledger yet (live before live init) has nothing to show: the switch leaves it out,
  // unless no account has one, when the first one's errors say so.
  const opened = accounts.data.filter((a) => a.capital !== null)
  const listed = opened.length > 0 ? opened : accounts.data
  // A saved id the backend no longer lists falls back to the first account.
  const account = listed.find((a) => a.id === chosen) ?? listed[0]
  if (!account) return <div className="px-3 py-6 text-muted">后端没有返回任何账户</div>
  const select = (id: string) => {
    setChosen(id)
    saveAccountId(id)
  }
  return (
    <StrategyContext value={vars}>
      <Shell account={account} accounts={listed} select={select} />
    </StrategyContext>
  )
}
