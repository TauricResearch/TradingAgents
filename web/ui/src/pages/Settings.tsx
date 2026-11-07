import { useState, type FormEvent } from 'react'
import type {
  CurrentModels,
  CurrentTier,
  LlmSettingsRequest,
  ModelChange,
  ModelsResponse,
  Price,
  ProviderInfo,
  Tier,
  TierSelection,
} from '../api'
import { ApiError, postJson } from '../api'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { DataTable, type Column } from '../components/DataTable'
import { ModelPicker } from '../components/ModelPicker'
import { Panel } from '../components/Panel'
import { ErrorBox, Loading } from '../components/Status'
import { fmtTime, fmtTimeFull } from '../format'
import { useFetch } from '../hooks'
import {
  ACCOUNT_LABEL,
  TIERS,
  draftOf,
  fmtPricePair,
  invalidOf,
  samePrice,
  selectionOf,
  type Draft,
} from '../llmSettings'

const CHIP = 'inline-block rounded-sm border px-1.5 text-[11px] leading-4'
const CHIP_PLAIN = `${CHIP} border-border bg-panel-2 text-fg`
const CHIP_WARN = `${CHIP} border-accent/60 bg-accent/15 text-accent`

type Drafts = Record<Tier, Draft>
type Selections = Record<Tier, TierSelection>

const draftsOf = (c: CurrentModels): Drafts => ({ deep: draftOf(c.deep), quick: draftOf(c.quick) })

const providerName = (providers: ProviderInfo[], id: string): string =>
  providers.find((p) => p.id === id)?.name ?? id

/** Another model, as opposed to the same model at another price. */
const switched = (a: TierSelection, b: TierSelection): boolean => a.model !== b.model || a.provider !== b.provider

const priceText = (price: Price | null): string => (price ? fmtPricePair(price) : '未设')

/** The request for the selections; null while one lacks a model ID or a price. */
function requestOf({ deep, quick }: Selections): LlmSettingsRequest | null {
  if (!deep.model || !quick.model || !deep.price || !quick.price) return null
  return { deep: { ...deep, price: deep.price }, quick: { ...quick, price: quick.price }, confirm: true }
}

/** One tier in the confirmation: "深度：A → B". */
function changeLine(label: string, before: TierSelection, after: TierSelection, providers: ProviderInfo[]): string {
  if (switched(before, after)) {
    if (before.provider === after.provider) return `${label}：${before.model} → ${after.model}`
    const named = (s: TierSelection) => `${s.model}（${providerName(providers, s.provider)}）`
    return `${label}：${named(before)} → ${named(after)}`
  }
  if (!samePrice(before.price, after.price)) {
    return `${label}：${after.model} 单价 ${priceText(before.price)} → ${priceText(after.price)}`
  }
  return `${label}：${after.model}（不变）`
}

function failureText(e: unknown): string {
  if (e instanceof ApiError) return `保存失败（HTTP ${e.status}）：${e.message}`
  return `保存失败，连不上后端：${e instanceof Error ? e.message : String(e)}`
}

function CurrentCard({ label, selection, providers }: { label: string; selection: CurrentTier; providers: ProviderInfo[] }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-sm border border-border bg-panel-2 px-3 py-2">
      <div className="flex items-baseline justify-between gap-3 text-[11px] text-muted">
        <span className="tracking-wide">{label}</span>
        <span className="truncate" title={selection.provider}>
          {providerName(providers, selection.provider)}
        </span>
      </div>
      <div className="num truncate text-[16px] leading-6 font-medium" title={selection.model}>
        {selection.model}
      </div>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px]">
        <span className="text-[11px] text-muted">单价</span>
        {selection.price ? (
          <>
            <span className="num">{fmtPricePair(selection.price)}</span>
            <span className="text-[11px] text-muted">输入 / 输出，美元每百万 token</span>
          </>
        ) : (
          <>
            <span className={CHIP_WARN}>未设</span>
            <span className="text-[11px] text-accent">费用核算和月度预算都靠它，请在下方补上</span>
          </>
        )}
      </div>
      {selection.price_note && <div className="text-[11px] text-muted">备注：{selection.price_note}</div>}
    </div>
  )
}

/** 已生效 once every account that ran used the selection; otherwise the accounts still behind. */
function AppliedNote({ applied }: { applied: Record<string, boolean> }) {
  const ran = Object.keys(applied)
  const behind = ran.filter((id) => !applied[id])
  if (ran.length > 0 && behind.length === 0) return <span className={CHIP_PLAIN}>已生效</span>
  return (
    <span className="flex flex-wrap items-center gap-x-1.5">
      <span className={CHIP_WARN}>下次运行生效</span>
      <span className="text-[11px]">
        {behind.length > 0
          ? `未生效：${behind.map((id) => ACCOUNT_LABEL[id] ?? id).join('、')}`
          : '还没有账户运行过'}
      </span>
    </span>
  )
}

function Current({ current, providers }: { current: CurrentModels; providers: ProviderInfo[] }) {
  return (
    <div className="flex flex-col gap-2.5">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {TIERS.map(({ key, label }) => (
          <CurrentCard key={key} label={label} selection={current[key]} providers={providers} />
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[12px] text-muted">
        <span className="flex items-center gap-1.5">
          来源 <span className={CHIP_PLAIN}>{current.source === 'env' ? '.env' : '设置'}</span>
        </span>
        {current.updated_at && (
          <span className="num" title={fmtTimeFull(current.updated_at)}>
            设置写入于 {fmtTime(current.updated_at)}
          </span>
        )}
        <AppliedNote applied={current.applied} />
      </div>
    </div>
  )
}

function SwitchForm({ data, onSaved }: { data: ModelsResponse; onSaved: (next: ModelsResponse) => void }) {
  const { current, providers } = data
  const [drafts, setDrafts] = useState<Drafts>(() => draftsOf(current))
  const [attempted, setAttempted] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const next: Selections = { deep: selectionOf(drafts.deep), quick: selectionOf(drafts.quick) }
  const changed = TIERS.some(
    ({ key }) => switched(current[key], next[key]) || !samePrice(current[key].price, next[key].price),
  )
  const anySwitched = TIERS.some(({ key }) => switched(current[key], next[key]))
  const request = requestOf(next)

  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setAttempted(request === null)
    setFailure(null)
    setSaved(false)
    if (request) {
      setConfirming(true)
      return
    }
    for (const { key } of TIERS) {
      const invalid = invalidOf(drafts[key])
      const field = (['custom', 'input', 'output'] as const).find((f) => invalid[f])
      if (field) {
        document.getElementById(`${key}-${field}`)?.focus()
        return
      }
    }
  }

  const save = () => {
    if (!request) return
    setBusy(true)
    postJson<ModelsResponse>('/api/settings/llm', request).then(
      (res) => {
        setDrafts(draftsOf(res.current))
        setConfirming(false)
        setBusy(false)
        setSaved(true)
        onSaved(res)
      },
      (err: unknown) => {
        setFailure(failureText(err))
        setConfirming(false)
        setBusy(false)
      },
    )
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {TIERS.map(({ key, label }) => (
          <ModelPicker
            key={key}
            tier={key}
            label={label}
            providers={providers}
            current={current[key]}
            draft={drafts[key]}
            onChange={(d) => setDrafts((all) => ({ ...all, [key]: d }))}
            invalid={attempted ? invalidOf(drafts[key]) : null}
          />
        ))}
      </div>

      {saved && (
        <div
          role="status"
          className="flex items-center gap-3 rounded-sm border border-border border-l-2 border-l-accent bg-panel-2 px-3 py-2"
        >
          <span className="min-w-0 flex-1">已保存，日频下次 00:05 UTC、日内下个整点生效</span>
          <button
            type="button"
            onClick={() => setSaved(false)}
            aria-label="关闭提示"
            className="shrink-0 px-1 text-[15px] leading-none text-muted hover:text-fg"
          >
            ×
          </button>
        </div>
      )}
      {failure && (
        <div role="alert" className="rounded-sm border border-down/50 bg-down/10 px-3 py-2 text-[12px] text-down">
          {failure}
        </div>
      )}

      <div className="flex items-center justify-end gap-3">
        {!changed && <span className="text-[11px] text-muted">没有改动</span>}
        <button
          type="submit"
          disabled={!changed || busy}
          className="rounded-sm border border-accent bg-accent/15 px-4 py-1 text-[12px] font-medium text-accent hover:bg-accent/25 disabled:cursor-not-allowed disabled:border-border disabled:bg-transparent disabled:text-muted"
        >
          保存
        </button>
      </div>

      {confirming && (
        <ConfirmDialog
          title={anySwitched ? '确认切换模型' : '确认修改单价'}
          confirmLabel={busy ? '保存中…' : anySwitched ? '确定切换' : '确定保存'}
          busy={busy}
          onConfirm={save}
          onCancel={() => setConfirming(false)}
        >
          <p>
            {anySwitched
              ? '切换后日频和日内两个账户的验证期都会从下一次运行起重新计时，之前的绩效比较不再成立。'
              : '只改单价、不换模型，验证期不会重新计时；费用从下一次运行起按新单价核算。'}
          </p>
          <p className="num flex flex-col rounded-sm border border-border bg-bg/40 px-2 py-1.5 text-[12px]">
            {TIERS.map(({ key, label }, i) => (
              <span key={key}>
                {changeLine(label, current[key], next[key], providers)}
                {i < TIERS.length - 1 ? '；' : '。'}
              </span>
            ))}
          </p>
          <p>{anySwitched ? '确定切换？' : '确定保存？'}</p>
        </ConfirmDialog>
      )}
    </form>
  )
}

const historyColumns: Column<ModelChange>[] = [
  {
    key: 'at',
    header: '时间（UTC）',
    render: (h) => (
      <span className="num" title={fmtTimeFull(h.at)}>
        {fmtTime(h.at)}
      </span>
    ),
  },
  { key: 'deep', header: '深度', render: (h) => <span className="num">{h.deep}</span> },
  { key: 'quick', header: '快速', render: (h) => <span className="num">{h.quick}</span> },
  { key: 'note', header: '备注', className: 'min-w-48 whitespace-normal', render: (h) => h.note },
]

export function Settings() {
  const models = useFetch<ModelsResponse>('/api/models')
  // The reply of the latest save: the state after it, newer than the page's fetch.
  const [latest, setLatest] = useState<ModelsResponse | null>(null)
  const data = latest ?? models.data

  if (models.error && !data) return <ErrorBox error={models.error} onRetry={models.refresh} />
  if (!data) return <Loading />

  return (
    <div className="mx-auto flex max-w-[960px] flex-col gap-3">
      <div className="text-[12px] leading-relaxed text-muted">
        <p>这是看板唯一的写入入口，只改研判用的模型和单价，不动账户（ADR 0007）。</p>
        <p>保存后写入服务器的 settings.json，从下一次运行起生效；换模型会让日频和日内两个账户的验证期重新计时。</p>
      </div>

      <Panel title="当前模型">
        <Current current={data.current} providers={data.providers} />
      </Panel>

      <Panel title="切换模型">
        <SwitchForm data={data} onSaved={setLatest} />
      </Panel>

      <Panel title="变更历史" flush aside={data.history.length > 0 ? `${data.history.length} 条` : undefined}>
        <DataTable columns={historyColumns} rows={data.history} rowKey={(h, i) => `${h.at}-${i}`} empty="暂无变更" />
      </Panel>
    </div>
  )
}
