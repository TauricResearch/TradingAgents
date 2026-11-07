import { useAccount } from '../account'
import type { Accuracy, Equity } from '../api'
import { accountPath } from '../api'
import { AccuracyCard } from '../components/AccuracyCard'
import { EquityChart } from '../components/EquityChart'
import { Kpi, KpiStrip } from '../components/Kpi'
import { LatestCards } from '../components/LatestCards'
import { LatestSignals } from '../components/LatestSignals'
import { LlmCard } from '../components/LlmCard'
import { Num } from '../components/Num'
import { Panel } from '../components/Panel'
import { PerfTable } from '../components/PerfTable'
import { PositionsTable } from '../components/PositionsTable'
import { ErrorBox, Loading, StaleNote } from '../components/Status'
import { Welcome } from '../components/Welcome'
import { fmtDate, fmtDrawdown, fmtNum, fmtPct, fmtSigned, fmtTime, fmtUsdt, tone } from '../format'
import { useFetch } from '../hooks'

const REFRESH_MS = 60_000
const INSUFFICIENT = '样本不足'

export function Overview() {
  const { account, overview } = useAccount()
  const equity = useFetch<Equity>(accountPath(account.id, 'equity'), REFRESH_MS)
  // The intraday account settles no ratings, so there is no accuracy to fetch.
  const accuracy = useFetch<Accuracy>(account.intraday ? null : accountPath(account.id, 'accuracy'), REFRESH_MS * 5)

  if (overview.error && !overview.data) return <ErrorBox error={overview.error} onRetry={overview.refresh} />
  if (!overview.data) return <Loading />

  const ov = overview.data
  const perf = ov.performance.strategy
  const unrealized = ov.positions.reduce((acc, p) => acc + p.unrealized, 0)
  const noteFor = (x: number | null | undefined, ok = '') => (x === null || x === undefined ? INSUFFICIENT : ok)

  return (
    <div className="flex flex-col gap-3">
      <Welcome />
      <KpiStrip>
        <Kpi label="净值 USDT" value={fmtUsdt(ov.equity)} note={`现金 ${fmtUsdt(ov.cash)}`} help="equity" />
        <Kpi
          label="验证期累计"
          value={fmtPct(perf?.cumulative)}
          tone={tone(perf?.cumulative)}
          note={noteFor(perf?.cumulative, `峰值 ${fmtUsdt(ov.peak)}`)}
          help="cumulative"
        />
        <Kpi
          label="扣 LLM 后年化"
          value={fmtPct(perf?.annualized)}
          tone={tone(perf?.annualized)}
          note={noteFor(perf?.annualized)}
          help="annualized_net"
        />
        <Kpi label="Sharpe" value={fmtNum(perf?.sharpe)} note={noteFor(perf?.sharpe)} help="sharpe" />
        <Kpi
          label="最大回撤"
          value={fmtDrawdown(perf?.max_drawdown)}
          tone={perf && perf.max_drawdown > 0 ? 'down' : 'flat'}
          note={noteFor(perf?.max_drawdown, `当前 ${fmtDrawdown(ov.drawdown)}`)}
          help="max_drawdown"
        />
        <Kpi label="年化/回撤" value={fmtNum(perf?.calmar)} note={noteFor(perf?.calmar)} help="calmar" />
        <Kpi
          label="验证期天数"
          value={String(ov.days)}
          note={ov.validation_start ? `自 ${fmtDate(ov.validation_start)}` : '验证期未开始'}
          help="validation_days"
        />
      </KpiStrip>

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
          <Panel title="LLM 费用" help="llm_cost" className="flex-1">
            <LlmCard llm={ov.llm} intraday={account.intraday} />
          </Panel>
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Panel
          title="持仓"
          help="positions"
          className={account.intraday ? 'xl:col-span-3' : 'xl:col-span-2'}
          flush
          aside={
            ov.positions.length > 0 && (
              <span className="num">
                {ov.positions.length} 个合约 · 浮动盈亏 <Num value={unrealized} fmt={fmtSigned} />
              </span>
            )
          }
        >
          <PositionsTable positions={ov.positions} />
        </Panel>

        {!account.intraday && (
          <Panel title="评级准确度" help="accuracy" aside={<StaleNote error={accuracy.error} />}>
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
  )
}
