import { Navigate, Route, Routes } from 'react-router-dom'
import { AccountContext } from './account'
import type { Account, Overview } from './api'
import { accountPath } from './api'
import { TopBar } from './components/TopBar'
import { ErrorBox, Loading } from './components/Status'
import { useFetch } from './hooks'
import { History } from './pages/History'
import { Overview as OverviewPage } from './pages/Overview'
import { Research } from './pages/Research'
import { ResearchDetail } from './pages/ResearchDetail'

const OVERVIEW_REFRESH_MS = 60_000

/** Routes and layout for one account; the overview feed is shared via context. */
function Shell({ account }: { account: Account }) {
  const overview = useFetch<Overview>(accountPath(account.id, 'overview'), OVERVIEW_REFRESH_MS)
  return (
    <AccountContext value={{ account, overview }}>
      <TopBar />
      <main className="mx-auto max-w-[1500px] px-3 py-3">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/research" element={<Research />} />
          <Route path="/research/:coin/:date" element={<ResearchDetail />} />
          <Route path="/history" element={<History />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </AccountContext>
  )
}

export default function App() {
  const accounts = useFetch<Account[]>('/api/accounts')
  if (accounts.error && !accounts.data) {
    return <ErrorBox error={accounts.error} onRetry={accounts.refresh} />
  }
  if (!accounts.data) return <Loading />
  const account = accounts.data[0]
  if (!account) return <div className="px-3 py-6 text-muted">后端没有返回任何账户</div>
  return <Shell account={account} />
}
