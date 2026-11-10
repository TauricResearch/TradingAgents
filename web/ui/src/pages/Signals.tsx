import { useAccount } from '../account'
import type { Signal } from '../api'
import { accountPath } from '../api'
import type { Column } from '../components/DataTable'
import { FollowedChip } from '../components/FollowedChip'
import { Panel } from '../components/Panel'
import { SignalChip } from '../components/SignalChip'
import { StaleNote } from '../components/Status'
import { Table } from '../components/Table'
import { Time } from '../components/Time'
import { fmtInt, fmtUsd, truncate } from '../format'
import { useFetch } from '../hooks'

const REFRESH_MS = 60_000

const signalColumns: Column<Signal>[] = [
  { key: 'ts', header: '时间', render: (s) => <Time ts={s.ts} /> },
  { key: 'coin', header: '币', render: (s) => <span className="num font-medium">{s.coin}</span> },
  { key: 'signal', header: '信号', render: (s) => <SignalChip signal={s.signal} error={s.error} /> },
  {
    key: 'conviction',
    header: '信心',
    render: (s) =>
      s.conviction === null ? <span className="text-muted">—</span> : <span className="num">{s.conviction}/3</span>,
  },
  {
    key: 'reason',
    header: '理由',
    className: 'min-w-64 whitespace-normal',
    // A failed call has no reason, only the error; its full text is on hover.
    render: (s) =>
      s.reason ||
      (s.error && (
        <span className="text-down" title={s.error}>
          {truncate(s.error, 120)}
        </span>
      )),
  },
]

/** The intraday account pays for its signals; the columns of what each cost. */
const costColumns: Column<Signal>[] = [
  { key: 'tokens_in', header: 'tokens 进', align: 'right', render: (s) => fmtInt(s.tokens_in) },
  { key: 'tokens_out', header: 'tokens 出', align: 'right', render: (s) => fmtInt(s.tokens_out) },
  { key: 'cost', header: '费用', align: 'right', render: (s) => fmtUsd(s.cost_usd) },
]

/** The demo account follows the intraday signals: what it did about each in its hour. */
const followedColumn: Column<Signal> = {
  key: 'followed',
  header: 'Demo 执行',
  render: (s) => <FollowedChip followed={s.followed} />,
}

export function Signals() {
  const { account } = useAccount()
  const signals = useFetch<Signal[]>(accountPath(account.id, 'signals?limit=500'), REFRESH_MS)
  const columns = account.demo ? [...signalColumns, followedColumn] : [...signalColumns, ...costColumns]

  return (
    <Panel
      title={account.demo ? '跟随的信号 · 来自日内账户' : '信号记录'}
      help={account.demo ? 'followed' : undefined}
      aside={<StaleNote error={signals.error} />}
      flush
    >
      <Table state={signals} columns={columns} rowKey={(s, i) => `${s.ts}-${s.coin}-${i}`} />
    </Panel>
  )
}
