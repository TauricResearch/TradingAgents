/** Screening data layer — rules, enrichment, and sentiment for watchlist curation. */

import { DatabaseFactory } from "@lib/db"

// ── Types ────────────────────────────────────────────────────────────────────

export type ScreenField =
  | "pe_forward"
  | "eps_growth_1y"
  | "operating_margin"
  | "beta_1y"
  | "price_to_sales"
  | "sector"
  | "region"
  | "price"
  | "sentiment_score"
  // Pattern features (R08 — STL decomposition)
  | "trend_strength"
  | "trend_linearity"
  | "seasonality_strength"
  | "seasonality_stability"
  | "residual_acf1"
  | "spectral_entropy"
  | "is_stationary"

export type ScreenOperator = "gt" | "lt" | "eq" | "gte" | "lte" | "in" | "bottom_pct" | "top_pct"

export interface ScreenCondition {
  field: ScreenField
  operator: ScreenOperator
  value: number | string | string[]
}

export interface ScreeningRule {
  id: number
  name: string
  description: string | null
  enabled: number
  conditions: ScreenCondition[]
  priority: number
  created_at: string
  updated_at: string
}

export interface EnrichmentRow {
  ticker: string
  fetch_date: string
  pe_forward: number | null
  eps_growth_1y: number | null
  operating_margin: number | null
  beta_1y: number | null
  price_to_sales: number | null
  sector: string | null
  region: string | null
  source: string
  // Pattern features (R08 — STL decomposition)
  trend_strength: number | null
  trend_linearity: number | null
  seasonality_strength: number | null
  seasonality_stability: number | null
  residual_acf1: number | null
  spectral_entropy: number | null
  is_stationary: number | null
  created_at: string
}

export interface SentimentRow {
  id: number
  ticker: string
  published_date: string
  headline_text: string
  summary: string | null
  sentiment_score: number | null
  source: string | null
  enrichment_id: string
  created_at: string
}

// ── Screening Rules ──────────────────────────────────────────────────────────

export function listScreeningRules(): ScreeningRule[] {
  const db = DatabaseFactory.get()
  const rows = db
    .query("SELECT * FROM screening_rules ORDER BY priority DESC, name ASC")
    .all() as Array<ScreeningRule & { conditions: string }>

  return rows.map((r) => ({
    ...r,
    conditions: JSON.parse(r.conditions) as ScreenCondition[],
  }))
}

export function getScreeningRule(id: number): ScreeningRule | null {
  const db = DatabaseFactory.get()
  const row = db.query("SELECT * FROM screening_rules WHERE id = ?").get(id) as
    | (ScreeningRule & { conditions: string })
    | null

  if (!row) return null
  return { ...row, conditions: JSON.parse(row.conditions) as ScreenCondition[] }
}

export function createScreeningRule(
  name: string,
  conditions: ScreenCondition[],
  description?: string,
  priority = 0,
): number {
  const db = DatabaseFactory.get()
  const result = db
    .query(
      "INSERT INTO screening_rules (name, description, conditions, priority) VALUES (?, ?, ?, ?)",
    )
    .run(name, description ?? null, JSON.stringify(conditions), priority)
  return Number(result.lastInsertRowid)
}

export function deleteScreeningRule(id: number): boolean {
  const db = DatabaseFactory.get()
  const result = db.query("DELETE FROM screening_rules WHERE id = ?").run(id)
  return result.changes > 0
}

export function toggleScreeningRule(id: number, enabled: boolean): boolean {
  const db = DatabaseFactory.get()
  const result = db
    .query("UPDATE screening_rules SET enabled = ?, updated_at = datetime('now') WHERE id = ?")
    .run(enabled ? 1 : 0, id)
  return result.changes > 0
}

// ── Enrichment ───────────────────────────────────────────────────────────────

export function upsertEnrichment(enrichment: Omit<EnrichmentRow, "created_at">): void {
  const db = DatabaseFactory.get()
  db.query(
    `INSERT INTO watchlist_enrichment
     (ticker, fetch_date, pe_forward, eps_growth_1y, operating_margin, beta_1y, price_to_sales, sector, region, source)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(ticker, fetch_date) DO UPDATE SET
       pe_forward = excluded.pe_forward,
       eps_growth_1y = excluded.eps_growth_1y,
       operating_margin = excluded.operating_margin,
       beta_1y = excluded.beta_1y,
       price_to_sales = excluded.price_to_sales,
       sector = excluded.sector,
       region = excluded.region,
       source = excluded.source`,
  ).run(
    enrichment.ticker,
    enrichment.fetch_date,
    enrichment.pe_forward ?? null,
    enrichment.eps_growth_1y ?? null,
    enrichment.operating_margin ?? null,
    enrichment.beta_1y ?? null,
    enrichment.price_to_sales ?? null,
    enrichment.sector ?? null,
    enrichment.region ?? null,
    enrichment.source,
  )
}

export interface PatternFeatures {
  trend_strength: number
  trend_linearity: number
  seasonality_strength: number
  seasonality_stability: number
  residual_acf1: number
  spectral_entropy: number
  is_stationary: number
}

/** Upsert pattern features into an existing enrichment row. */
export function upsertPatternFeatures(
  ticker: string,
  fetchDate: string,
  features: PatternFeatures,
): void {
  const db = DatabaseFactory.get()
  db.query(
    `UPDATE watchlist_enrichment SET
       trend_strength = ?,
       trend_linearity = ?,
       seasonality_strength = ?,
       seasonality_stability = ?,
       residual_acf1 = ?,
       spectral_entropy = ?,
       is_stationary = ?
     WHERE ticker = ? AND fetch_date = ?`,
  ).run(
    features.trend_strength,
    features.trend_linearity,
    features.seasonality_strength,
    features.seasonality_stability,
    features.residual_acf1,
    features.spectral_entropy,
    features.is_stationary,
    ticker,
    fetchDate,
  )
}

// ── Normalization helpers ────────────────────────────────────────────────────────

// Raw DB rows have REAL columns as strings; normalize to numbers
type RawEnrichmentRow = {
  ticker: string
  fetch_date: string
  pe_forward: string | null
  eps_growth_1y: string | null
  operating_margin: string | null
  beta_1y: string | null
  price_to_sales: string | null
  sector: string | null
  region: string | null
  source: string
  trend_strength: string | null
  trend_linearity: string | null
  seasonality_strength: string | null
  seasonality_stability: string | null
  residual_acf1: string | null
  spectral_entropy: string | null
  is_stationary: string | null
  created_at: string
}

function normalizeEnrichmentRow(raw: RawEnrichmentRow): EnrichmentRow {
  return {
    ticker: raw.ticker,
    fetch_date: raw.fetch_date,
    pe_forward: raw.pe_forward != null ? parseFloat(raw.pe_forward) : null,
    eps_growth_1y: raw.eps_growth_1y != null ? parseFloat(raw.eps_growth_1y) : null,
    operating_margin: raw.operating_margin != null ? parseFloat(raw.operating_margin) : null,
    beta_1y: raw.beta_1y != null ? parseFloat(raw.beta_1y) : null,
    price_to_sales: raw.price_to_sales != null ? parseFloat(raw.price_to_sales) : null,
    sector: raw.sector,
    region: raw.region,
    source: raw.source,
    trend_strength: raw.trend_strength != null ? parseFloat(raw.trend_strength) : null,
    trend_linearity: raw.trend_linearity != null ? parseFloat(raw.trend_linearity) : null,
    seasonality_strength:
      raw.seasonality_strength != null ? parseFloat(raw.seasonality_strength) : null,
    seasonality_stability:
      raw.seasonality_stability != null ? parseFloat(raw.seasonality_stability) : null,
    residual_acf1: raw.residual_acf1 != null ? parseFloat(raw.residual_acf1) : null,
    spectral_entropy: raw.spectral_entropy != null ? parseFloat(raw.spectral_entropy) : null,
    is_stationary: raw.is_stationary != null ? parseFloat(raw.is_stationary) : null,
    created_at: raw.created_at,
  }
}

type RawSentimentRow = {
  id: number
  ticker: string
  published_date: string
  headline_text: string
  summary: string | null
  sentiment_score: string | null
  source: string | null
  enrichment_id: string
  created_at: string
}

function normalizeSentimentRow(raw: RawSentimentRow): SentimentRow {
  return {
    id: raw.id,
    ticker: raw.ticker,
    published_date: raw.published_date,
    headline_text: raw.headline_text,
    summary: raw.summary,
    sentiment_score: raw.sentiment_score != null ? parseFloat(raw.sentiment_score) : null,
    source: raw.source,
    enrichment_id: raw.enrichment_id,
    created_at: raw.created_at,
  }
}

export function getLatestEnrichment(ticker: string): EnrichmentRow | null {
  const db = DatabaseFactory.get()
  const raw = db
    .query("SELECT * FROM watchlist_enrichment WHERE ticker = ? ORDER BY fetch_date DESC LIMIT 1")
    .get(ticker) as RawEnrichmentRow | undefined
  if (!raw) return null
  return normalizeEnrichmentRow(raw)
}

export function getAllEnrichment(): EnrichmentRow[] {
  const db = DatabaseFactory.get()
  const rows = db
    .query("SELECT * FROM watchlist_enrichment ORDER BY ticker, fetch_date DESC")
    .all() as RawEnrichmentRow[]
  return rows.map(normalizeEnrichmentRow)
}

// ── Sentiment ────────────────────────────────────────────────────────────────

export function insertSentiment(headline: Omit<SentimentRow, "id" | "created_at">): number {
  const db = DatabaseFactory.get()
  const result = db
    .query(
      `INSERT INTO watchlist_news_sentiment
       (ticker, published_date, headline_text, summary, sentiment_score, source, enrichment_id)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    )
    .run(
      headline.ticker,
      headline.published_date,
      headline.headline_text,
      headline.summary,
      headline.sentiment_score,
      headline.source,
      headline.enrichment_id,
    )
  return Number(result.lastInsertRowid)
}

export function getSentimentForTicker(ticker: string): SentimentRow[] {
  const db = DatabaseFactory.get()
  const rows = db
    .query("SELECT * FROM watchlist_news_sentiment WHERE ticker = ? ORDER BY published_date DESC")
    .all(ticker) as RawSentimentRow[]
  return rows.map(normalizeSentimentRow)
}

export function getSentimentSummary(ticker: string): { count: number; avg_score: number | null } {
  const db = DatabaseFactory.get()
  const row = db
    .query(
      "SELECT COUNT(*) as count, AVG(sentiment_score) as avg_score FROM watchlist_news_sentiment WHERE ticker = ?",
    )
    .get(ticker) as { count: number; avg_score: number | null }
  return row
}

export function pruneOldSentiment(days = 30): number {
  const db = DatabaseFactory.get()
  const result = db
    .query("DELETE FROM watchlist_news_sentiment WHERE published_date < date('now', ?)")
    .run(`-${days} days`)
  return result.changes
}

// ── Screening History ─────────────────────────────────────────────────────────

export function saveScreeningHistory(tickers: string[], ruleCount: number): number {
  const db = DatabaseFactory.get()
  const date: string = new Date().toISOString().substring(0, 10)
  const result = db
    .query(
      "INSERT INTO watchlist_screenings (run_date, tickers_matched, rule_count) VALUES (?, ?, ?)",
    )
    .run(date, JSON.stringify(tickers), ruleCount)
  return Number(result.lastInsertRowid)
}

export function getRecentScreenings(limit = 10): Array<{
  id: number
  run_date: string
  tickers_matched: string[]
  rule_count: number
  created_at: string
}> {
  const db = DatabaseFactory.get()
  const rows = db
    .query("SELECT * FROM watchlist_screenings ORDER BY run_date DESC LIMIT ?")
    .all(limit) as Array<{
    id: number
    run_date: string
    tickers_matched: string
    rule_count: number
    created_at: string
  }>

  return rows.map((r) => ({
    ...r,
    tickers_matched: JSON.parse(r.tickers_matched) as string[],
  }))
}
