import { useAccount } from '../account'
import type { Signal } from '../api'
import { accountPath } from '../api'
import { coinLabel, fmtUsd } from '../format'
import { useFetch } from '../hooks'
import { Panel } from './Panel'
import { SignalChip } from './SignalChip'
import { Empty, ErrorBox, Loading, StaleNote } from './Status'
import { Time } from './Time'

const REFRESH_MS = 60_000

function Row({ signal }: { signal: Signal }) {
  return (
    <li className="flex flex-col gap-1 border-b border-border/60 px-3 py-2 last:border-b-0">
      <div className="flex min-w-0 items-center gap-2">
        <span className="num w-10 shrink-0 text-[14px] font-semibold" title={signal.coin}>
          {coinLabel(signal.coin)}
        </span>
        <SignalChip signal={signal.signal} error={signal.error} />
        {signal.conviction !== null && (
          <span className="num shrink-0 text-[11px] text-muted">信心 {signal.conviction}/3</span>
        )}
        <span className="num ml-auto shrink-0 text-[11px] text-muted" title="该币这次信号的 LLM 费用">
          {fmtUsd(signal.cost_usd)}
        </span>
      </div>
      <div className="pl-12 text-[12px] text-muted">
        <Time ts={signal.ts} />
      </div>
    </li>
  )
}

/** The intraday account's newest signal per coin, in watchlist order. */
export function LatestSignals() {
  const { account } = useAccount()
  const signals = useFetch<Signal[]>(accountPath(account.id, 'signals?limit=60'), REFRESH_MS)

  // Newest first, so the first match of a coin is its latest signal.
  const latest = signals.data
    ? account.watchlist.flatMap((w) => {
        const s = signals.data?.find((x) => x.coin === w.research)
        return s ? [s] : []
      })
    : []

  return (
    <Panel title="最近信号" aside={<StaleNote error={signals.error} />} flush>
      {signals.error && !signals.data ? (
        <ErrorBox error={signals.error} onRetry={signals.refresh} />
      ) : !signals.data ? (
        <Loading />
      ) : latest.length === 0 ? (
        <Empty label="暂无信号" />
      ) : (
        <ul className="flex flex-col">
          {latest.map((s) => (
            <Row key={s.coin} signal={s} />
          ))}
        </ul>
      )}
    </Panel>
  )
}
