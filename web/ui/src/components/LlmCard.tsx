import type { LlmUsage } from '../api'
import { fmtUsd } from '../format'
import { Help } from './Help'

export function LlmCard({ llm, intraday = false }: { llm: LlmUsage; intraday?: boolean }) {
  // The intraday account has no monthly cap: its signal costs are already taken off its performance.
  const capText = intraday
    ? '无上限，已从绩效扣除'
    : llm.cap === null
      ? `上限未定（已观察 ${llm.learned_days}/${llm.learning_days} 天）`
      : fmtUsd(llm.cap)
  const used = llm.cap !== null && llm.cap > 0 ? Math.min(1, llm.month / llm.cap) : null

  return (
    <div className="flex flex-col gap-2">
      <dl className="grid grid-cols-3 gap-2">
        <div>
          <dt className="text-[11px] text-muted">今日</dt>
          <dd className="num text-[16px]">{fmtUsd(llm.today)}</dd>
        </div>
        <div>
          <dt className="text-[11px] text-muted">本月</dt>
          <dd className="num text-[16px]">{fmtUsd(llm.month)}</dd>
        </div>
        <div className="min-w-0">
          <dt className="flex items-center gap-1 text-[11px] text-muted">
            上限
            {!intraday && <Help k="budget_cap" align="end" />}
          </dt>
          <dd className={`num ${intraday || llm.cap === null ? 'text-[12px] leading-6 text-muted' : 'text-[16px]'}`}>
            {capText}
          </dd>
        </div>
      </dl>
      {used !== null && (
        <div className="h-1 w-full overflow-hidden rounded-sm bg-panel-2" title={`本月已用 ${(used * 100).toFixed(0)}%`}>
          <div
            className={`h-full ${used >= 0.9 ? 'bg-down' : used >= 0.7 ? 'bg-accent' : 'bg-muted'}`}
            style={{ width: `${used * 100}%` }}
          />
        </div>
      )}
      {llm.unknown && <div className="text-[11px] text-accent">有调用费用未知，没算进去</div>}
      <div className="num text-[11px] text-muted">
        {intraday ? 'UTC 日' : '研判日'} {llm.trade_date}
      </div>
    </div>
  )
}
