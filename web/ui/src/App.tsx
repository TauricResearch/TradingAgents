import { useMemo, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AccountContext } from './account'
import type { Account, Overview, Strategy } from './api'
import { accountPath } from './api'
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

/** Routes and layout for one account; the overview feed is shared via context. */
function Shell({ account, accounts, select }: ShellProps) {
  const overview = useFetch<Overview>(accountPath(account.id, 'overview'), OVERVIEW_REFRESH_MS)
  return (
    <AccountContext value={{ account, accounts, select, overview }}>
      <TopBar />
      <main className="mx-auto max-w-[1500px] px-3 py-3">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/research" element={<Research />} />
          <Route path="/research/:coin/:date" element={<ResearchDetail />} />
          {account.intraday && <Route path="/signals" element={<Signals />} />}
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
  // A saved id the backend no longer lists falls back to the first account.
  const account = accounts.data.find((a) => a.id === chosen) ?? accounts.data[0]
  if (!account) return <div className="px-3 py-6 text-muted">后端没有返回任何账户</div>
  const select = (id: string) => {
    setChosen(id)
    saveAccountId(id)
  }
  return (
    <StrategyContext value={vars}>
      {/* Keyed by account: switching resets the pages' local state along with the overview feed. */}
      <Shell key={account.id} account={account} accounts={accounts.data} select={select} />
    </StrategyContext>
  )
}
