import type { ReactNode } from 'react'
import type { Account, Execution } from '../api'
import { coinLabel, fmtNum, fmtSigned, fmtUsdt } from '../format'
import { Num, Side } from './Num'
import { Time } from './Time'

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] text-muted">{label}</dt>
      <dd className="num text-[15px]">{children}</dd>
    </div>
  )
}

/** An exchange account's last reconciliation with the exchange: what the exchange held, had pending, what did not add up, and why it is paused. */
export function ExecutionCard({ execution: ex, account }: { execution: Execution; account: Account }) {
  const resume = `python -m trader ${account.id} resume`
  return (
    <div className="flex flex-col gap-3 text-[13px]">
      <dl className="grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-4">
        <Field label="交易所权益">{fmtUsdt(ex.equity)}</Field>
        <Field label="钱包余额">{fmtUsdt(ex.cash)}</Field>
        <Field label="最近对账">{ex.synced_at ? <Time ts={ex.synced_at} /> : <span className="text-muted">尚未对账</span>}</Field>
        <Field label="最近跟随的小时">
          {ex.decided_hour ? <Time ts={ex.decided_hour} /> : <span className="text-muted">尚未交易</span>}
        </Field>
      </dl>

      {ex.halted && (
        <div className="rounded-sm border border-down/40 bg-down/10 px-2 py-1 text-down">
          {account.live
            ? '已熔断，实验结束：每次对账都平掉交易所里剩下的仓位、撤掉止损单；live 的熔断不再解除'
            : '熔断中：交易所持仓已平、止损单已撤，等待人工解除'}
        </div>
      )}

      {ex.paused && (
        <div className="flex flex-col gap-1 rounded-sm border border-accent/40 bg-accent/10 px-2 py-1">
          <div className="text-accent">
            {ex.shadow_run
              ? '影子运行中，还没解锁：不下单，每小时照常对账，记下本该下的单'
              : '暂停中：不下新单，仓位和止损单原样保留；每小时照常对账，记下本该下的单'}
          </div>
          {ex.pause_reasons.map((r) => (
            <div key={r.text}>
              {r.text}
              {r.since && (
                <span className="text-muted">
                  （<Time ts={r.since} /> 起）
                </span>
              )}
            </div>
          ))}
          <div className="text-[11px] text-muted">
            {ex.shadow_run ? `解锁要满足实验规定的条件，在终端运行 ${resume}` : `查明原因后在终端运行 ${resume} 解除`}
          </div>
        </div>
      )}

      {ex.problems.length > 0 ? (
        <ul className="flex flex-col gap-1 rounded-sm border border-down/40 bg-down/10 px-2 py-1">
          {ex.problems.map((p) => (
            <li key={p} className="text-down">
              {p}
            </li>
          ))}
          <li className="text-[11px] text-muted">有问题的小时不下单，直到对账干净</li>
        </ul>
      ) : (
        ex.synced_at && !ex.paused && <div className="text-[12px] text-muted">上次对账账本与交易所一致</div>
      )}

      <div>
        <div className="mb-1 text-[11px] text-muted">交易所持仓</div>
        {ex.positions.length === 0 ? (
          <div className="text-muted">空仓</div>
        ) : (
          <table className="w-full text-[12px]">
            <thead className="text-[11px] text-muted">
              <tr>
                <th className="text-left font-normal">合约</th>
                <th className="text-right font-normal">张数</th>
                <th className="text-right font-normal">均价</th>
                <th className="text-right font-normal">未实现</th>
                <th className="text-right font-normal">杠杆</th>
                <th className="text-right font-normal">强平价</th>
                <th className="text-right font-normal">止损</th>
              </tr>
            </thead>
            <tbody>
              {ex.positions.map((p) => (
                <tr key={p.inst} className="border-t border-border">
                  <td className="py-0.5">
                    <span className="mr-1">{coinLabel(p.coin ?? p.inst)}</span>
                    {p.contracts !== null && <Side qty={p.contracts} />}
                  </td>
                  <td className="num text-right">{p.contracts === null ? '—' : fmtSigned(p.contracts, 2)}</td>
                  <td className="num text-right">{fmtNum(p.avg_price)}</td>
                  <td className="text-right">
                    <Num value={p.unrealized} fmt={fmtSigned} />
                  </td>
                  <td className="num text-right">
                    {p.margin_mode ?? ''} {p.leverage === null ? '—' : `${fmtNum(p.leverage, 0)}×`}
                  </td>
                  <td className="num text-right">{fmtNum(p.liquidation_price)}</td>
                  <td className="num text-right">{p.stop === null ? <span className="text-accent">待挂</span> : fmtNum(p.stop)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div>
        <div className="mb-1 text-[11px] text-muted">挂在交易所的止损单</div>
        {ex.stops.length === 0 ? (
          <div className="text-muted">{ex.positions.length === 0 ? '无' : '无（持仓没有止损单保护）'}</div>
        ) : (
          <ul className="flex flex-col gap-0.5 text-[12px]">
            {ex.stops.map((s) => (
              <li key={s.client_id ?? `${s.inst}-${s.trigger}`} className="num">
                {coinLabel(s.coin ?? s.inst)} {s.side === 'sell' ? '卖出' : s.side === 'buy' ? '买入' : ''} {fmtNum(s.contracts, 2)} 张，触发价{' '}
                {fmtNum(s.trigger)}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
