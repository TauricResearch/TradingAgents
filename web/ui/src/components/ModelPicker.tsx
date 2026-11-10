import type { ModelInfo, Price, ProviderInfo, Tier, TierSelection } from '../api'
import { fmtDate } from '../format'
import {
  CUSTOM,
  draftOf,
  fmtPricePair,
  modelsFor,
  priceFields,
  samePrice,
  selectionOf,
  type Draft,
  type Invalid,
} from '../llmSettings'

export const CONTROL =
  'min-w-0 rounded-sm border border-border bg-bg px-2 py-1 text-[13px] text-fg focus:border-accent focus:outline-none aria-invalid:border-down'

interface Props {
  tier: Tier
  label: string
  providers: ProviderInfo[]
  /** The tier's selection in effect. */
  current: TierSelection
  draft: Draft
  onChange: (draft: Draft) => void
  /** Fields to flag once a save was attempted; null before. */
  invalid: Invalid | null
}

interface Note {
  text: string
  href: string | null
  /** The price is missing and has to be typed. */
  warn: boolean
  /** The price table's remark, appended to the official price. */
  remark?: string | null
}

/** Where the price in the fields comes from, under them. */
function priceNote(draft: Draft, listed: ModelInfo | undefined, price: Price | null): Note {
  const missing = price === null
  if (draft.choice === CUSTOM) {
    return { text: missing ? '自定义模型：单价要手填' : '自定义模型：手填的单价', href: null, warn: missing }
  }
  if (listed?.price) {
    const shown = samePrice(price, listed.price) ? '' : ` ${fmtPricePair(listed.price)}`
    const asOf = listed.price_as_of ? ` · 截至 ${fmtDate(listed.price_as_of)}` : ''
    return { text: `官方定价${shown}${asOf}`, href: listed.price_source, warn: false, remark: listed.price_note }
  }
  if (listed) {
    const text = missing ? '官方定价表里没有这个模型，单价要手填' : '官方定价表里没有这个模型'
    return { text, href: null, warn: missing }
  }
  // Not listed: the configured model, which the catalog lacks.
  return { text: missing ? '当前模型的单价未设，要手填' : '当前配置的单价', href: null, warn: missing }
}

/** One tier of the switch form: provider, then a listed model or a typed ID, then the price. Field ids are `<tier>-<field>`. */
export function ModelPicker({ tier, label, providers, current, draft, onChange, invalid }: Props) {
  const id = (field: string) => `${tier}-${field}`
  const models = modelsFor(providers.find((p) => p.id === draft.provider), tier)
  const onCurrentProvider = draft.provider === current.provider
  const listed = models.find((m) => m.id === draft.choice)
  const note = priceNote(draft, listed, selectionOf(draft).price)

  const pickProvider = (provider: string) => {
    if (provider === current.provider) {
      onChange(draftOf(current))
      return
    }
    const first = modelsFor(providers.find((p) => p.id === provider), tier)[0]
    onChange({ provider, choice: first?.id ?? CUSTOM, custom: '', ...priceFields(first?.price ?? null) })
  }

  const pickModel = (choice: string) => {
    const official = models.find((m) => m.id === choice)?.price ?? null
    const configured = onCurrentProvider && choice === current.model ? current.price : null
    onChange({ ...draft, choice, ...priceFields(choice === CUSTOM ? null : (configured ?? official)) })
  }

  return (
    <div role="group" aria-labelledby={id('title')} className="flex min-w-0 flex-col gap-2.5 rounded-sm border border-border p-3">
      <h3 id={id('title')} className="text-[12px] font-medium tracking-wide text-fg">
        {label}
      </h3>

      <div className="flex flex-col gap-1">
        <label htmlFor={id('provider')} className="text-[11px] text-muted">
          provider
        </label>
        <select
          id={id('provider')}
          value={draft.provider}
          onChange={(e) => pickProvider(e.target.value)}
          className={`${CONTROL} w-full`}
        >
          {!providers.some((p) => p.id === current.provider) && (
            <option value={current.provider}>{current.provider}</option>
          )}
          {providers.map((p) => (
            <option key={p.id} value={p.id} disabled={!p.has_key}>
              {p.has_key ? p.name : `${p.name}（未配置 ${p.key_env ?? 'API 密钥'}）`}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor={id('model')} className="text-[11px] text-muted">
          模型
        </label>
        <select
          id={id('model')}
          value={draft.choice}
          onChange={(e) => pickModel(e.target.value)}
          className={`${CONTROL} w-full`}
        >
          {onCurrentProvider && !models.some((m) => m.id === current.model) && (
            <option value={current.model}>{`${current.model}（当前）`}</option>
          )}
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {onCurrentProvider && m.id === current.model ? `${m.label}（当前）` : m.label}
            </option>
          ))}
          <option value={CUSTOM}>自定义模型 ID…</option>
        </select>
        {listed && listed.label !== listed.id && <span className="num text-[11px] text-muted">{listed.id}</span>}
        {draft.choice === CUSTOM && (
          <input
            id={id('custom')}
            aria-label={`${label}模型 ID`}
            value={draft.custom}
            onChange={(e) => onChange({ ...draft, custom: e.target.value })}
            placeholder="provider 文档里的模型 ID"
            spellCheck={false}
            autoComplete="off"
            aria-invalid={invalid?.custom || undefined}
            className={`${CONTROL} num w-full`}
          />
        )}
        {invalid?.custom && <span className="text-[11px] text-down">填写模型 ID</span>}
      </div>

      <div className="flex flex-col gap-1">
        <span id={id('price')} className="text-[11px] text-muted">
          单价（美元 / 百万 token）
        </span>
        <div role="group" aria-labelledby={id('price')} className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {(['input', 'output'] as const).map((field) => (
            <label key={field} className="flex items-center gap-1.5">
              <span className="text-[12px] text-muted">{field === 'input' ? '输入' : '输出'}</span>
              <input
                id={id(field)}
                type="number"
                inputMode="decimal"
                min={0}
                step="any"
                value={draft[field]}
                onChange={(e) => onChange({ ...draft, [field]: e.target.value })}
                aria-invalid={invalid?.[field] || undefined}
                className={`${CONTROL} num w-24 text-right`}
              />
            </label>
          ))}
        </div>
        <div className="text-[11px] text-muted">
          {note.href ? (
            <a
              href={note.href}
              target="_blank"
              rel="noreferrer"
              className="underline decoration-dotted underline-offset-2 hover:text-fg"
            >
              {note.text} ↗
            </a>
          ) : (
            <span className={note.warn ? 'text-accent' : undefined}>{note.text}</span>
          )}
          {note.remark && ` · ${note.remark}`}
        </div>
        {invalid && (invalid.input || invalid.output) && (
          <span className="text-[11px] text-down">填写输入和输出单价：不小于 0 的数字</span>
        )}
      </div>
    </div>
  )
}
