import { ApiError } from '../api'

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

/** Small inline notice when a refresh failed but stale data is still shown. */
export function StaleNote({ error }: { error: Error | null }) {
  if (!error) return null
  return (
    <span className="text-[11px] text-down" title={error.message}>
      刷新失败，显示的是上次数据
    </span>
  )
}
