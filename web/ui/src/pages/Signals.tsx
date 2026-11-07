import { useAccount } from '../account'
import type { Signal } from '../api'
import { accountPath } from '../api'
import type { Column } from '../components/DataTable'
import { Panel } from '../components/Panel'
import { SignalChip } from '../components/SignalChip'
import { StaleNote } from '../components/Status'
import { Table } from '../components/Table'
import { Time } from '../components/Time'
import { fmtInt, fmtUsd } from '../format'
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
  { key: 'reason', header: '理由', className: 'min-w-64 whitespace-normal', render: (s) => s.reason },
  { key: 'tokens_in', header: 'tokens 进', align: 'right', render: (s) => fmtInt(s.tokens_in) },
  { key: 'tokens_out', header: 'tokens 出', align: 'right', render: (s) => fmtInt(s.tokens_out) },
  { key: 'cost', header: '费用', align: 'right', render: (s) => fmtUsd(s.cost_usd) },
]

export function Signals() {
  const { account } = useAccount()
  const signals = useFetch<Signal[]>(accountPath(account.id, 'signals?limit=500'), REFRESH_MS)

  return (
    <Panel title="信号记录" aside={<StaleNote error={signals.error} />} flush>
      <Table state={signals} columns={signalColumns} rowKey={(s, i) => `${s.ts}-${s.coin}-${i}`} />
    </Panel>
  )
}
