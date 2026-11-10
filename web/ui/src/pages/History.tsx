import { useSearchParams } from 'react-router-dom'
import { useAccount } from '../account'
import type { Attempt, Daily, DailyRow, Fill, FillReason, Funding, LedgerEvent } from '../api'
import { accountPath } from '../api'
import type { Column } from '../components/DataTable'
import { Num } from '../components/Num'
import { Panel } from '../components/Panel'
import { RatingChip } from '../components/RatingChip'
import { StaleNote } from '../components/Status'
import { Table } from '../components/Table'
import { Tabs } from '../components/Tabs'
import { Time } from '../components/Time'
import { daySpan } from '../daily'
import { fmtDay, fmtInt, fmtPct, fmtQty, fmtSigned, fmtTimeFull, fmtUsd, fmtUsdt } from '../format'
import { useFetch } from '../hooks'

type TabKey = 'daily' | 'fills' | 'funding' | 'attempts' | 'events'

const dailyColumns: Column<DailyRow>[] = [
  {
    key: 'date',
    header: '日期（UTC）',
    render: (d) => (
      <span className="num" title={`${daySpan(d)}\n起点 ${fmtTimeFull(d.start_ts)}`}>
        {fmtDay(d.start_ts)}
        {d.partial && <span className="ml-1 text-[11px] text-muted">进行中</span>}
      </span>
    ),
  },
  { key: 'open', header: '期初', align: 'right', render: (d) => fmtUsdt(d.open) },
  { key: 'close', header: '期末', align: 'right', render: (d) => fmtUsdt(d.close) },
  { key: 'pnl', header: '盈亏', align: 'right', render: (d) => <Num value={d.pnl} fmt={fmtSigned} /> },
  { key: 'pct', header: '收益率', align: 'right', render: (d) => <Num value={d.pct} fmt={fmtPct} /> },
  { key: 'fills', header: '成交', align: 'right', render: (d) => fmtInt(d.fills) },
  { key: 'funding', header: '资金费', align: 'right', render: (d) => <Num value={d.funding} fmt={fmtSigned} /> },
  { key: 'llm_cost', header: 'AI 费用', align: 'right', render: (d) => fmtUsd(d.llm_cost) },
]

const REASON: Record<FillReason, { label: string; cls: string }> = {
  trade: { label: '调仓', cls: 'border-border bg-panel-2 text-muted' },
  stop: { label: '止损', cls: 'border-down/50 bg-down/15 text-down' },
  kill: { label: '熔断', cls: 'border-accent/60 bg-accent/15 text-accent' },
}

function ReasonChip({ reason }: { reason: FillReason }) {
  const r = REASON[reason] ?? { label: reason, cls: 'border-border bg-panel-2 text-muted' }
  return <span className={`inline-block rounded-sm border px-1.5 text-[11px] leading-4 ${r.cls}`}>{r.label}</span>
}

const fillColumns: Column<Fill>[] = [
  { key: 'ts', header: '时间', render: (f) => <Time ts={f.ts} /> },
  { key: 'inst', header: '合约', render: (f) => <span className="num">{f.inst}</span> },
  {
    key: 'side',
    header: '方向',
    render: (f) =>
      f.qty >= 0 ? <span className="text-up">买入</span> : <span className="text-down">卖出</span>,
  },
  { key: 'qty', header: '数量', align: 'right', render: (f) => <Num value={f.qty} fmt={fmtQty} /> },
  { key: 'price', header: '价格', align: 'right', render: (f) => fmtUsdt(f.price) },
  { key: 'fee', header: '手续费', align: 'right', render: (f) => fmtUsdt(f.fee, 4) },
  { key: 'reason', header: '原因', help: 'fill_reason', render: (f) => <ReasonChip reason={f.reason} /> },
  {
    key: 'trade_date',
    header: '研判日',
    render: (f) => <span className="num text-muted">{f.trade_date ?? '—'}</span>,
  },
]

const fundingColumns: Column<Funding>[] = [
  { key: 'ts', header: '时间', render: (f) => <Time ts={f.ts} /> },
  { key: 'inst', header: '合约', render: (f) => <span className="num">{f.inst}</span> },
  { key: 'coin', header: '币', render: (f) => <span className="num">{f.coin}</span> },
  { key: 'rate', header: '费率', align: 'right', render: (f) => fmtPct(f.rate, 4) },
  { key: 'amount', header: '金额', align: 'right', render: (f) => <Num value={f.amount} fmt={fmtSigned} /> },
]

const attemptColumns: Column<Attempt>[] = [
  { key: 'trade_date', header: '研判日', render: (a) => <span className="num">{a.trade_date}</span> },
  { key: 'coin', header: '币', render: (a) => <span className="num font-medium">{a.coin}</span> },
  { key: 'ts', header: '时间', render: (a) => <Time ts={a.ts} /> },
  {
    key: 'result',
    header: '评级 / 错误',
    className: 'max-w-[420px] whitespace-normal',
    render: (a) =>
      a.rating !== null ? <RatingChip rating={a.rating} /> : <RatingChip rating={null} state="failed" error={a.error} />,
  },
  { key: 'tokens_in', header: 'tokens 进', help: 'tokens', align: 'right', render: (a) => fmtInt(a.tokens_in) },
  { key: 'tokens_out', header: 'tokens 出', help: 'tokens', align: 'right', render: (a) => fmtInt(a.tokens_out) },
  { key: 'cost', header: '费用', align: 'right', render: (a) => fmtUsd(a.cost_usd) },
]

const eventColumns: Column<LedgerEvent>[] = [
  { key: 'ts', header: '时间', render: (e) => <Time ts={e.ts} /> },
  {
    key: 'kind',
    header: '类型',
    render: (e) => (
      <span className="num inline-block rounded-sm border border-border bg-panel-2 px-1.5 text-[11px] leading-4 text-muted">
        {e.kind}
      </span>
    ),
  },
  { key: 'text', header: '内容', className: 'whitespace-normal', render: (e) => e.text },
]

export function History() {
  const { account } = useAccount()
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab')

  const dailyRaw = useFetch<Daily>(accountPath(account.id, 'daily?limit=500'))
  // The tab shows the day rows; the months stay on the overview.
  const daily = { ...dailyRaw, data: dailyRaw.data?.days ?? null }
  const fills = useFetch<Fill[]>(accountPath(account.id, 'fills?limit=500'))
  const funding = useFetch<Funding[]>(accountPath(account.id, 'funding?limit=500'))
  // The intraday account has no daily research, so nothing to fetch for the attempts tab.
  const attempts = useFetch<Attempt[]>(account.intraday ? null : accountPath(account.id, 'attempts?limit=500'))
  const events = useFetch<LedgerEvent[]>(accountPath(account.id, 'events?limit=500'))

  const tabs = [
    { key: 'daily' as const, label: '每日收益', count: daily.data?.length },
    { key: 'fills' as const, label: '成交', count: fills.data?.length },
    { key: 'funding' as const, label: '资金费', count: funding.data?.length },
    { key: 'attempts' as const, label: '研判记录', count: attempts.data?.length },
    { key: 'events' as const, label: '事件', count: events.data?.length },
  ].filter((t) => !(account.intraday && t.key === 'attempts'))
  // A tab in the URL that is not among this account's tabs falls back to the fills.
  const active: TabKey = tabs.find((t) => t.key === raw)?.key ?? 'fills'
  const current = { daily, fills, funding, attempts, events }[active]
  // An intraday fill's date is the UTC day of its hour, not a research day.
  const fillCols = account.intraday
    ? fillColumns.map((c) => (c.key === 'trade_date' ? { ...c, header: 'UTC 日' } : c))
    : fillColumns

  return (
    <div className="flex flex-col gap-3">
      <Tabs tabs={tabs} active={active} onChange={(k) => setParams(k === 'fills' ? {} : { tab: k })} />
      {/* Tab keys double as help keys. */}
      <Panel
        flush
        aside={
          <span className="num flex flex-wrap items-center gap-x-3">
            <StaleNote error={current.error} />
            {active === 'daily' && <span>UTC 日 · 北京 08:00 起 · 盈亏不含 AI 费用</span>}
          </span>
        }
        title={tabs.find((t) => t.key === active)?.label}
        help={active}
      >
        {active === 'daily' && <Table state={daily} columns={dailyColumns} rowKey={(d) => d.date} />}
        {active === 'fills' && <Table state={fills} columns={fillCols} rowKey={(f, i) => `${f.ts}-${f.inst}-${i}`} />}
        {active === 'funding' && (
          <Table state={funding} columns={fundingColumns} rowKey={(f, i) => `${f.ts}-${f.inst}-${i}`} />
        )}
        {active === 'attempts' && (
          <Table state={attempts} columns={attemptColumns} rowKey={(a, i) => `${a.trade_date}-${a.coin}-${a.ts}-${i}`} />
        )}
        {active === 'events' && <Table state={events} columns={eventColumns} rowKey={(e, i) => `${e.ts}-${i}`} />}
      </Panel>
    </div>
  )
}
