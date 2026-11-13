import { useAccount } from '../account'
import type { Execution } from '../api'
import { Help } from './Help'
import { Time } from './Time'

function State({ ex }: { ex: Execution }) {
  if (ex.halted) {
    return <div className="text-down">已熔断，实验结束：每次对账都平掉交易所里剩下的仓位、撤掉止损单；live 的熔断不再解除。</div>
  }
  if (!ex.paused) return <div className="text-muted">运行中：每小时跟随日内信号，在交易所自动下单。</div>
  return (
    <div className="flex flex-col gap-0.5">
      <div className="text-accent">
        {ex.shadow_run
          ? '影子运行中，还没解锁：每小时照常对账，记下本该下的单，但不下单。'
          : '暂停中：不下新单，仓位和止损单原样保留；每小时照常对账，记下本该下的单。'}
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
    </div>
  )
}

/** The live account trades real money (ADR 0010): said above every page, with the state its last reconciliation left it in. */
export function LiveBanner() {
  const { execution } = useAccount()
  return (
    <div role="note" className="mb-3 flex flex-col gap-1 rounded-sm border border-down/60 bg-down/10 px-3 py-2 text-[13px]">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="rounded-sm bg-down px-1.5 py-px text-[11px] font-semibold text-bg">真钱</span>
        <span>live 账户在 OKX 正式环境的子账户里交易，盈亏都是真的。看板只读：解锁、解除暂停和熔断都在终端用命令做。</span>
        <Help k="live" />
      </div>
      {execution.data && <State ex={execution.data} />}
    </div>
  )
}
