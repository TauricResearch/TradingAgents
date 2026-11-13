import { ApiError, type MarketStatus } from '../api'
import { fmtTime } from '../format'

export function Loading({ label = '加载中…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 px-3 py-6 text-muted" role="status">
      <span className="inline-block size-2 animate-pulse rounded-full bg-accent" />
      {label}
    </div>
  )
}

export function Empty({ label = '暂无记录' }: { label?: string }) {
  return <div className="px-3 py-6 text-center text-muted">{label}</div>
}

/** Human message for a failed request. */
function describeError(error: Error): { title: string; detail: string } {
  if (error instanceof ApiError) {
    if (error.status === 404) return { title: '没有这条记录', detail: error.message }
    if (error.status >= 502 && error.status <= 504) {
      return { title: '连不上后端：先运行 python -m web.api', detail: error.message }
    }
    return { title: `请求失败（HTTP ${error.status}）`, detail: error.message }
  }
  // fetch() rejects with a TypeError when the server is unreachable.
  return { title: '连不上后端：先运行 python -m web.api', detail: error.message }
}

export function ErrorBox({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const { title, detail } = describeError(error)
  return (
    <div className="m-3 rounded-sm border border-down/50 bg-down/10 px-3 py-2" role="alert">
      <div className="font-medium text-down">{title}</div>
      <div className="mt-0.5 num text-[11px] text-muted">{detail}</div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 rounded-sm border border-border bg-panel px-2 py-0.5 text-[11px] text-fg hover:border-muted"
        >
          重试
        </button>
      )}
    </div>
  )
}

/**
 * Banner while the API gets no usable quotes from OKX: prices shown are the last
 * usable ones it got, and what it never got shows as "—". Nothing while the market
 * is fine.
 */
export function MarketNote({ market }: { market: MarketStatus | undefined }) {
  if (!market || market.ok) return null
  return (
    <div
      className="rounded-sm border border-accent/50 bg-accent/10 px-3 py-1.5 text-[12px] text-fg"
      role="status"
      title={market.error ?? undefined}
    >
      <span className="font-medium text-accent">行情暂不可用</span>
      {market.since && <span className="num text-muted">（自 {fmtTime(market.since)} 起拿不到 OKX 的可用报价）</span>}
      ：净值和现价按最后拿到的报价显示，没拿到过的显示“—”；账本里的现金、持仓、成交不受影响。
    </div>
  )
}

/** Small inline notice when a refresh failed but stale data is still shown. */
export function StaleNote({ error }: { error: Error | null }) {
  if (!error) return null
  return (
    <span className="text-[11px] text-down" title={error.message}>
      刷新失败，显示的是上次数据
    </span>
  )
}
