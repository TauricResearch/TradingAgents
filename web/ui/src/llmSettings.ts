// The settings page's LLM form (ADR 0007): one draft per tier, and the helpers its parts share.

import type { ModelInfo, Price, ProviderInfo, Tier, TierSelection } from './api'
import { fmtDate, fmtNum, fmtUsd } from './format'

export const TIERS: { key: Tier; label: string }[] = [
  { key: 'deep', label: '深度' },
  { key: 'quick', label: '快速' },
]

/** Account ids as the settings page names them; an unknown id shows as is. */
export const ACCOUNT_LABEL: Record<string, string> = { paper: '日频', intraday: '日内' }

/** Model select value of the free-text model ID; no provider's model ID has parentheses. */
export const CUSTOM = '(custom)'

/** One tier's form state; the prices stay text while being typed. */
export interface Draft {
  provider: string
  /** A listed model ID, or CUSTOM. */
  choice: string
  custom: string
  input: string
  output: string
}

/** The price fields holding `price`, or blank. */
export const priceFields = (price: Price | null): Pick<Draft, 'input' | 'output'> =>
  price ? { input: String(price[0]), output: String(price[1]) } : { input: '', output: '' }

export const draftOf = (s: TierSelection): Draft => ({
  provider: s.provider,
  choice: s.model,
  custom: '',
  ...priceFields(s.price),
})

/** The models a provider offers for the tier, in its order. */
export const modelsFor = (provider: ProviderInfo | undefined, tier: Tier): ModelInfo[] =>
  provider?.models.filter((m) => m.modes.includes(tier)) ?? []

/** A price field as a number >= 0; null when blank or not a number. */
function parsePrice(text: string): number | null {
  if (text.trim() === '') return null
  const x = Number(text)
  return Number.isFinite(x) && x >= 0 ? x : null
}

/** What the draft would save; the price is null until both fields hold one. */
export function selectionOf(d: Draft): TierSelection {
  const input = parsePrice(d.input)
  const output = parsePrice(d.output)
  return {
    provider: d.provider,
    model: d.choice === CUSTOM ? d.custom.trim() : d.choice,
    price: input === null || output === null ? null : [input, output],
  }
}

/** The fields of a draft that cannot be saved as they are. */
export interface Invalid {
  custom: boolean
  input: boolean
  output: boolean
}

export const invalidOf = (d: Draft): Invalid => ({
  custom: d.choice === CUSTOM && d.custom.trim() === '',
  input: parsePrice(d.input) === null,
  output: parsePrice(d.output) === null,
})

export const samePrice = (a: Price | null, b: Price | null): boolean =>
  a === null || b === null ? a === b : a[0] === b[0] && a[1] === b[1]

/** USD per million tokens, keeping the decimals price lists quote: $5.00, $0.075. */
export function fmtPrice(x: number): string {
  const decimals = String(x).split('.')[1]?.length ?? 0
  return decimals <= 2 ? fmtUsd(x) : `$${fmtNum(x, Math.min(decimals, 4))}`
}

/** "$5.00 / $25.00": input / output. */
export const fmtPricePair = (price: Price): string => `${fmtPrice(price[0])} / ${fmtPrice(price[1])}`

/** Days after which an official price unread since is shown as to be checked (ADR 0007). */
export const STALE_PRICE_DAYS = 90

/** Why a listed price is to be checked, for `today` (an ISO date); null while it is current. */
export function stalePrice(listed: ModelInfo, today: string): string | null {
  if (listed.price_until && listed.price_until < today) {
    return `该价格 ${fmtDate(listed.price_until)} 已到期，待核对官网`
  }
  if (listed.price_as_of) {
    const days = (Date.parse(today) - Date.parse(listed.price_as_of)) / 86_400_000
    if (days > STALE_PRICE_DAYS) return `价格读取已超过 ${STALE_PRICE_DAYS} 天，待核对官网`
  }
  return null
}
