import type { Followed } from '../api'

/** What the demo account did about a signal in its hour; the titles say what each means. */
const FOLLOWED: Record<Followed, { label: string; cls: string; title: string }> = {
  executed: { label: '已执行', cls: 'border-up/50 bg-up/15 text-up', title: '这个小时按这个信号在交易所成交了' },
  no_change: { label: '无需调仓', cls: 'border-border bg-panel-2 text-muted', title: '这个小时处理过，目标仓位和持仓差别不到调仓门槛' },
  skipped: { label: '未赶上', cls: 'border-accent/50 bg-accent/10 text-accent', title: '等到截止时间日内账户还没决定，这个小时没有交易' },
  blocked: { label: '对账阻塞', cls: 'border-accent/50 bg-accent/10 text-accent', title: '对账发现问题，这个小时不下单（见总览的执行对账）' },
  paused: { label: '暂停中', cls: 'border-accent/50 bg-accent/10 text-accent', title: '账户暂停，这个小时只记下本该下的单，不下单（原因见总览的执行对账）' },
  failed: { label: '下单失败', cls: 'border-down/50 bg-down/15 text-down', title: '订单被交易所拒绝、被程序拒绝或没有成交（见历史页的事件）' },
  pending: { label: '待处理', cls: 'border-border bg-panel-2 text-muted', title: 'Demo 还没跑到这个小时（每小时第 10 分运行）' },
}

/** Null means the signal is from before the demo account existed. */
export function FollowedChip({ followed }: { followed: Followed | null | undefined }) {
  if (!followed) return <span className="text-muted">—</span>
  const f = FOLLOWED[followed]
  return (
    <span
      className={`inline-flex max-w-full items-center rounded-sm border px-1.5 py-px text-[11px] font-medium leading-5 ${f.cls}`}
      title={f.title}
    >
      {f.label}
    </span>
  )
}
