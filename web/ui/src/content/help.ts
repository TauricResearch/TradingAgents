/**
 * One-line explanations behind the `?` marks, each pointing at the guide section
 * that says more. `text` may use the same `{{name}}` placeholders as the guide.
 */

import type { GuideSectionId } from './guide'

export type HelpKey =
  // top bar
  | 'drawdown'
  | 'processed_to'
  // overview KPIs
  | 'equity'
  | 'cumulative'
  | 'annualized_net'
  | 'sharpe'
  | 'max_drawdown'
  | 'calmar'
  | 'validation_days'
  // overview panels
  | 'equity_chart'
  | 'performance'
  | 'latest_research'
  | 'rating'
  | 'positions'
  | 'llm_cost'
  | 'budget_cap'
  | 'accuracy'
  | 'settled'
  | 'hit_rate'
  | 'mean_alpha'
  // positions table columns
  | 'side'
  | 'qty'
  | 'entry'
  | 'price'
  | 'notional'
  | 'unrealized'
  | 'stop'
  | 'stop_distance'
  // research detail sections, in pipeline order
  | 's_market'
  | 's_sentiment'
  | 's_news'
  | 's_fundamentals'
  | 's_debate'
  | 's_plan'
  | 's_trader'
  | 's_risk'
  | 's_decision'
  | 'tokens'
  // history tabs
  | 'fills'
  | 'fill_reason'
  | 'funding'
  | 'attempts'
  | 'events'

export interface HelpEntry {
  text: string
  section: GuideSectionId
}

export const HELP: Record<HelpKey, HelpEntry> = {
  drawdown: { text: '', section: 'risk' },
  processed_to: { text: '', section: 'daily-cycle' },
  equity: { text: '', section: 'overview-page' },
  cumulative: { text: '', section: 'overview-page' },
  annualized_net: { text: '', section: 'overview-page' },
  sharpe: { text: '', section: 'overview-page' },
  max_drawdown: { text: '', section: 'overview-page' },
  calmar: { text: '', section: 'overview-page' },
  validation_days: { text: '', section: 'validation' },
  equity_chart: { text: '', section: 'overview-page' },
  performance: { text: '', section: 'validation' },
  latest_research: { text: '', section: 'research' },
  rating: { text: '', section: 'sizing' },
  positions: { text: '', section: 'overview-page' },
  llm_cost: { text: '', section: 'overview-page' },
  budget_cap: { text: '', section: 'overview-page' },
  accuracy: { text: '', section: 'validation' },
  settled: { text: '', section: 'validation' },
  hit_rate: { text: '', section: 'validation' },
  mean_alpha: { text: '', section: 'validation' },
  side: { text: '', section: 'perps' },
  qty: { text: '', section: 'overview-page' },
  entry: { text: '', section: 'overview-page' },
  price: { text: '', section: 'overview-page' },
  notional: { text: '', section: 'perps' },
  unrealized: { text: '', section: 'overview-page' },
  stop: { text: '', section: 'risk' },
  stop_distance: { text: '', section: 'risk' },
  s_market: { text: '', section: 'research-page' },
  s_sentiment: { text: '', section: 'research-page' },
  s_news: { text: '', section: 'research-page' },
  s_fundamentals: { text: '', section: 'research-page' },
  s_debate: { text: '', section: 'research-page' },
  s_plan: { text: '', section: 'research-page' },
  s_trader: { text: '', section: 'research-page' },
  s_risk: { text: '', section: 'research-page' },
  s_decision: { text: '', section: 'research-page' },
  tokens: { text: '', section: 'history-page' },
  fills: { text: '', section: 'history-page' },
  fill_reason: { text: '', section: 'history-page' },
  funding: { text: '', section: 'perps' },
  attempts: { text: '', section: 'history-page' },
  events: { text: '', section: 'history-page' },
}
