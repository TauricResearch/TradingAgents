import type { ResearchSummary } from '../api'
import { Panel } from '../components/Panel'
import { ResearchList } from '../components/ResearchList'
import { ErrorBox, Loading } from '../components/Status'
import { fmtUsd } from '../format'
import { useFetch } from '../hooks'

export function Research() {
  const list = useFetch<ResearchSummary[]>('/api/research')

  if (list.error && !list.data) return <ErrorBox error={list.error} onRetry={list.refresh} />
  if (!list.data) return <Loading />

  const total = list.data.reduce((acc, r) => acc + (r.cost_usd ?? 0), 0)
  return (
    <Panel
      title="研判记录"
      aside={
        <span className="num">
          {list.data.length} 条 · LLM 费用合计 {fmtUsd(total)}
        </span>
      }
      flush
      className="mx-auto max-w-[980px]"
    >
      <ResearchList items={list.data} />
    </Panel>
  )
}
