import { useAccount } from '../account'
import type { Accuracy, Equity, Today } from '../api'
import { accountPath } from '../api'
import { AccuracyCard } from '../components/AccuracyCard'
import { EquityChart } from '../components/EquityChart'
import { Help } from '../components/Help'
import { Kpi, KpiStrip } from '../components/Kpi'
import { LatestCards } from '../components/LatestCards'
import { LatestSignals } from '../components/LatestSignals'
import { LlmCard } from '../components/LlmCard'
import { Num } from '../components/Num'
import { Panel } from '../components/Panel'
import { PerfTable } from '../components/PerfTable'
import { ExposureBar, PositionsTable } from '../components/PositionsTable'
import { ErrorBox, Loading, MarketNote, StaleNote } from '../components/Status'
import { Welcome } from '../components/Welcome'
import { fmtDate, fmtDay, fmtDrawdown, fmtNum, fmtPct, fmtSigned, fmtTime, fmtTimeFull, fmtUsdt, tone } from '../format'
import { useFetch } from '../hooks'

const REFRESH_MS = 60_000

/**
 * Where the day is measured from: today's UTC midnight, or the last snapshot written
 * when today's is not yet. Short, the cell is narrow; the hover has the Beijing clock.
 */
function todayNote(today: Today) {
  if (!today.since) return '尚无零点快照'
  const utcToday = new Date().toISOString().slice(0, 10)
  const from = today.since.slice(0, 10) === utcToday ? '自 UTC 00:00' : `自 ${fmtDay(today.since)} 零点`
  const text = today.pnl === null ? `无报价 · ${from}` : `${fmtPct(today.pct)} · ${from}`
  return <span title={`起点 ${fmtTimeFull(today.since)}`}>{text}</span>
}

export function Overview() {
  const { account, overview } = useAccount()
  const equity = useFetch<Equity>(accountPath(account.id, 'equity'), REFRESH_MS)
  // The intraday account settles no ratings, so there is no accuracy to fetch.
  const accuracy = useFetch<Accuracy>(account.intraday ? null : accountPath(account.id, 'accuracy'), REFRESH_MS * 5)

  if (overview.error && !overview.data) return <ErrorBox error={overview.error} onRetry={overview.refresh} />
  if (!overview.data) return <Loading />

  const ov = overview.data
  const t = ov.totals

  return (
    <div className="flex flex-col gap-3">
      <Welcome />
      <MarketNote market={ov.market} />
      <KpiStrip>
        <Kpi label="总资产 USDT" value={fmtUsdt(ov.equity)} note={`本金 ${fmtUsdt(ov.capital)}`} help="equity" />
        <Kpi label="今日盈亏（北京 08:00 起）" value={fmtSigned(ov.today.pnl)} tone={tone(ov.today.pnl)} note={todayNote(ov.today)} help="today_pnl" />
        <Kpi
          label="未实现盈亏"
          value={fmtSigned(t.unrealized)}
          tone={tone(t.unrealized)}
          note={ov.positions.length === 0 ? '无持仓' : t.unrealized === null ? '有合约无报价' : `${ov.positions.length} 个合约`}
          help="unrealized_total"
        />
        <Kpi label="已实现盈亏" value={fmtSigned(t.realized)} tone={tone(t.realized)} note="含手续费、资金费" help="realized" />
        <Kpi label="现金 USDT" value={fmtUsdt(ov.cash)} note="本金 + 已实现盈亏" help="cash" />
        <Kpi
          label="持仓名义"
          value={fmtUsdt(t.notional)}
          note={t.leverage === null ? '无报价' : `杠杆 ${fmtNum(t.leverage)}x`}
          help="notional_total"
        />
        <Kpi
          label="累计盈亏"
          value={fmtSigned(t.pnl)}
          tone={tone(t.pnl)}
          note={t.pnl_pct === null ? '无报价' : `${fmtPct(t.pnl_pct)} · 自开户`}
          help="total_pnl"
        />
      </KpiStrip>

      <Panel
        title="持仓"
        help="positions"
        flush
        aside={
          ov.positions.length > 0 && (
            <span className="num">
              浮动盈亏 <Num value={t.unrealized} fmt={fmtSigned} />
            </span>
          )
        }
      >
        <ExposureBar positions={ov.positions} totals={t} />
        <PositionsTable positions={ov.positions} totals={t} />
      </Panel>

      <div className="grid gap-3 xl:grid-cols-3">
        <Panel
          title="净值曲线"
          help="equity_chart"
          className="xl:col-span-2"
          aside={
            <span className="num flex flex-wrap items-center gap-x-3">
              <StaleNote error={equity.error} />
              {equity.data && (
                <span title={equity.data.live.ts}>
                  实时净值 <span className="text-fg">{fmtUsdt(equity.data.live.equity)}</span> ·{' '}
                  {fmtTime(equity.data.live.ts)}
                </span>
              )}
            </span>
          }
        >
          <div className="num mb-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted">
            <span className="inline-flex items-center gap-1">
              <span>
                验证期 <span className="text-fg">{ov.days}</span> 天
                {ov.validation_start ? ` · 自 ${fmtDate(ov.validation_start)}` : ' · 未开始'}
              </span>
              <Help k="validation_days" size="xs" />
            </span>
            <span>
              峰值 <span className="text-fg">{fmtUsdt(ov.peak)}</span>
            </span>
            <span>
              当前回撤 <span className={ov.drawdown != null && ov.drawdown > 0 ? 'text-down' : 'text-fg'}>{fmtDrawdown(ov.drawdown)}</span>
            </span>
          </div>
          {equity.error && !equity.data ? (
            <ErrorBox error={equity.error} onRetry={equity.refresh} />
          ) : !equity.data ? (
            <Loading />
          ) : (
            <EquityChart points={equity.data.points} />
          )}
          <div className="mt-2 border-t border-border pt-1">
            <PerfTable performance={ov.performance} />
          </div>
        </Panel>

        <div className="flex flex-col gap-3">
          {account.intraday ? (
            <LatestSignals />
          ) : (
            ov.latest && (
              <Panel
                title={`最近研判 · 研判日 ${ov.latest.trade_date}`}
                help="latest_research"
                aside={ov.latest.executed ? '已执行调仓' : <span className="text-accent">尚未执行</span>}
                flush
              >
                <LatestCards latest={ov.latest} />
              </Panel>
            )
          )}
          {/* The `?` text is about the monthly cap, which the intraday account does not have. */}
          <Panel title="LLM 费用" help={account.intraday ? undefined : 'llm_cost'}>
            <LlmCard llm={ov.llm} intraday={account.intraday} />
          </Panel>
          {!account.intraday && (
            <Panel title="评级准确度" help="accuracy" className="flex-1" aside={<StaleNote error={accuracy.error} />}>
              {accuracy.error && !accuracy.data ? (
                <ErrorBox error={accuracy.error} onRetry={accuracy.refresh} />
              ) : !accuracy.data ? (
                <Loading />
              ) : (
                <AccuracyCard accuracy={accuracy.data} />
              )}
            </Panel>
          )}
        </div>
      </div>
    </div>
  )
}
