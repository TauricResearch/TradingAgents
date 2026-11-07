// `{{name}}` placeholders in the guide and help copy, filled from GET /api/strategy
// so the numbers in the text always match the code that trades.

import type { Strategy } from '../api'

const ANALYST_NAMES: Record<string, string> = {
  market: '市场',
  social: '社媒',
  news: '新闻',
  fundamentals: '基本面',
}

/** Number with trailing zeros dropped: 2.5 → "2.5", 1 → "1", 0.05 → "0.05". */
const plain = (x: number): string => x.toFixed(10).replace(/\.?0+$/, '')

/** Fraction as a percentage: 0.02 → "2%", 0.0005 → "0.05%". */
const pct = (x: number): string => `${plain(x * 100)}%`

/** Rating weight with its sign and a real minus: 1 → "+1", -0.25 → "−0.25". */
function signed(x: number): string {
  if (x === 0) return '0'
  return (x < 0 ? '\u2212' : '+') + plain(Math.abs(x))
}

const coinOf = (ticker: string): string => ticker.split('-')[0]

export function strategyVars(s: Strategy): Record<string, string> {
  const coins = s.watchlist.map(coinOf)
  const weight = (rating: string): string => {
    const w = s.rating_weights[rating]
    return typeof w === 'number' ? signed(w) : '?'
  }
  return {
    coins: coins.join('、'),
    coin_count: String(coins.length),
    risk_per_unit_pct: pct(s.risk_per_unit),
    stop_atr_mult: plain(s.stop_atr_mult),
    atr_days: String(s.atr_days),
    w_buy: weight('Buy'),
    w_overweight: weight('Overweight'),
    w_underweight: weight('Underweight'),
    w_sell: weight('Sell'),
    max_coin_exposure: plain(s.max_coin_exposure),
    max_gross_exposure: plain(s.max_gross_exposure),
    rebalance_threshold: plain(s.rebalance_threshold),
    taker_fee_pct: pct(s.taker_fee),
    slippage_pct: pct(s.slippage),
    kill_drawdown_pct: pct(s.kill_drawdown),
    max_attempts: String(s.max_attempts),
    retry_wait_min: plain(s.retry_wait_seconds / 60),
    budget_learning_days: String(s.budget_learning_days),
    budget_headroom: plain(s.budget_headroom),
    benchmark: s.benchmark,
    benchmark_coin: coinOf(s.benchmark),
    holding_days: String(s.holding_period_days),
    analysts: s.analysts.map((a) => ANALYST_NAMES[a] ?? a).join('、'),
    analyst_count: String(s.analysts.length),
    deep_model: s.deep_model,
    quick_model: s.quick_model,
  }
}

const PLACEHOLDER = /\{\{\s*(\w+)\s*\}\}/g
const warned = new Set<string>()

/**
 * Replace `{{name}}` with `vars[name]`. Unknown names stay as written; in development
 * each is reported once, but not while `vars` is still empty (strategy not loaded yet).
 */
export function fill(text: string, vars: Record<string, string>): string {
  const loaded = Object.keys(vars).length > 0
  return text.replace(PLACEHOLDER, (match: string, name: string) => {
    const value = vars[name]
    if (value !== undefined) return value
    if (import.meta.env.DEV && loaded && !warned.has(name)) {
      warned.add(name)
      console.warn(`content: unknown placeholder {{${name}}}`)
    }
    return match
  })
}
