/** @jsxImportSource hono/jsx */

import { Hono } from "hono"
import { DatabaseFactory } from "@lib/db"
import {
  getAllEnrichment,
  getRecentScreenings,
  getScreeningRule,
  getSentimentSummary,
  listScreeningRules,
  type EnrichmentRow,
  type ScreeningRule,
} from "../lib/screening-data"
import { type CandidateData, detectShockStocks, screenCandidates } from "../lib/screening-engine"

export const screeningsRouter = new Hono()

// ── Types ─────────────────────────────────────────────────────────────────────

interface MatchResult {
  ticker: string
  exchange: string
  stage: string
  priority: string
  matched_rules: string[]
  match_reasons: string[]
  priority_score: number
  enrichment: EnrichmentRow | null
  sentiment_score: number | null
  sentiment_count: number
}

interface ScreenResult {
  matches: MatchResult[]
  total_candidates: number
  matched_count: number
  rules_evaluated: number
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function getSentimentAvg(ticker: string): { score: number | null; count: number } {
  const db = DatabaseFactory.get()
  const row = db
    .query(
      "SELECT COUNT(*) as count, AVG(sentiment_score) as avg_score FROM watchlist_news_sentiment WHERE ticker = ?",
    )
    .get(ticker) as { count: number; avg_score: number | null }
  return { score: row.avg_score, count: row.count }
}

function sentimentLabel(score: number | null): string {
  if (score === null) return "—"
  if (score >= 0.3) return "bullish"
  if (score <= -0.3) return "bearish"
  return "neutral"
}

// ── GET /api/screenings/results — run screening rules, return matches ─────────

screeningsRouter.get("/results", (c) => {
  const db = DatabaseFactory.get()

  const rules = listScreeningRules()
  const stageFilter = c.req.query("stage")?.split(",").filter(Boolean)

  const candidateRows = db
    .query(
      `SELECT w.ticker, w.exchange, w.stage, w.priority, e.*
       FROM watchlist w
       LEFT JOIN watchlist_enrichment e ON w.ticker = e.ticker
       WHERE w.stage != 'acquired'
       ORDER BY w.priority DESC, w.ticker`,
    )
    .all() as Array<
    { ticker: string; exchange: string; stage: string; priority: string } & Record<string, unknown>
  >

  const candidates: CandidateData[] = candidateRows.map((r) => {
    const sent = getSentimentAvg(r.ticker)
    return {
      ticker: r.ticker,
      exchange: r.exchange,
      stage: r.stage,
      priority: r.priority,
      enrichment: r.fetch_date
        ? ({
            ticker: r.ticker,
            fetch_date: r.fetch_date as string,
            pe_forward: r.pe_forward as number | null,
            eps_growth_1y: r.eps_growth_1y as number | null,
            operating_margin: r.operating_margin as number | null,
            beta_1y: r.beta_1y as number | null,
            price_to_sales: r.price_to_sales as number | null,
            sector: r.sector as string | null,
            region: r.region as string | null,
            source: r.source as string,
            trend_strength: null,
            trend_linearity: null,
            seasonality_strength: null,
            seasonality_stability: null,
            residual_acf1: null,
            spectral_entropy: null,
            is_stationary: null,
            created_at: r.created_at as string,
          })
        : null,
      sentiment_avg: sent.score,
    }
  })

  const result = screenCandidates({ candidates, rules, stageFilter })

  const enriched = result.matches.map((m) => {
    const sent = getSentimentAvg(m.ticker)
    return { ...m, sentiment_score: sent.score, sentiment_count: sent.count }
  })

  return c.json({ ...result, matches: enriched })
})

// ── GET /api/screenings/results/html — screening results as HTML panel ────────

screeningsRouter.get("/results/html", (c) => {
  const db = DatabaseFactory.get()
  const rules = listScreeningRules()

  const candidateRows = db
    .query(
      `SELECT w.ticker, w.exchange, w.stage, w.priority, e.*
       FROM watchlist w
       LEFT JOIN watchlist_enrichment e ON w.ticker = e.ticker
       WHERE w.stage != 'acquired'
       ORDER BY w.priority DESC, w.ticker`,
    )
    .all() as Array<
    { ticker: string; exchange: string; stage: string; priority: string } & Record<string, unknown>
  >

  const candidates: CandidateData[] = candidateRows.map((r) => {
    const sent = getSentimentAvg(r.ticker)
    return {
      ticker: r.ticker,
      exchange: r.exchange,
      stage: r.stage,
      priority: r.priority,
      enrichment: r.fetch_date
        ? ({
            ticker: r.ticker,
            fetch_date: r.fetch_date as string,
            pe_forward: r.pe_forward as number | null,
            eps_growth_1y: r.eps_growth_1y as number | null,
            operating_margin: r.operating_margin as number | null,
            beta_1y: r.beta_1y as number | null,
            price_to_sales: r.price_to_sales as number | null,
            sector: r.sector as string | null,
            region: r.region as string | null,
            source: r.source as string,
            trend_strength: null,
            trend_linearity: null,
            seasonality_strength: null,
            seasonality_stability: null,
            residual_acf1: null,
            spectral_entropy: null,
            is_stationary: null,
            created_at: r.created_at as string,
          })
        : null,
      sentiment_avg: sent.score,
    }
  })

  const result = screenCandidates({ candidates, rules })
  const matches = result.matches.map((m) => {
    const sent = getSentimentAvg(m.ticker)
    return { ...m, sentiment_score: sent.score, sentiment_count: sent.count }
  })

  const hasResults = matches.length > 0

  return c.html(
    <section class="panel screening-panel" id="screening-panel">
      <div class="screening-header">
        <h4>Screening Results</h4>
        {hasResults ? (
          <span class="badge">{matches.length} matched</span>
        ) : (
          <span class="badge secondary">no rules active</span>
        )}
      </div>

      {!hasResults ? (
        <p class="empty-state">
          No candidates match current screening rules. Run{" "}
          <code>trading screen create</code> to define rules, then{" "}
          <code>trading screen enrich --all</code> to populate fundamental data.
        </p>
      ) : (
        <table class="screening-table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Stage</th>
              <th>Score</th>
              <th>Rules</th>
              <th>Sentiment</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {matches.map((m) => (
              <tr key={m.ticker}>
                <td class="ticker">{m.ticker}</td>
                <td>
                  <span class={`stage-chip stage-${m.stage}`}>{m.stage}</span>
                </td>
                <td class="score">{m.priority_score}</td>
                <td class="rules">{m.matched_rules.join(", ")}</td>
                <td>
                  <span class={`sentiment-chip ${sentimentLabel(m.sentiment_score)}`}>
                    {sentimentLabel(m.sentiment_score)}
                    {m.sentiment_count > 0 && (
                      <span class="sentiment-count">({m.sentiment_count})</span>
                    )}
                  </span>
                </td>
                <td class="reason">{m.match_reasons[0] ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>,
  )
})

// ── GET /api/screenings/shock — shock stock detection ─────────────────────────

screeningsRouter.get("/shock", (c) => {
  const db = DatabaseFactory.get()

  const priceDropPct = parseFloat(c.req.query("drop") ?? "10")
  const minMarginPct = parseFloat(c.req.query("margin") ?? "20")
  const maxPSRatio = parseFloat(c.req.query("ps") ?? "5")

  const candidateRows = db
    .query(
      `SELECT w.ticker, w.exchange, w.stage, w.priority, e.*
       FROM watchlist w
       LEFT JOIN watchlist_enrichment e ON w.ticker = e.ticker
       WHERE w.stage != 'acquired'
       ORDER BY w.priority DESC, w.ticker`,
    )
    .all() as Array<
    { ticker: string; exchange: string; stage: string; priority: string } & Record<string, unknown>
  >

  const candidates: CandidateData[] = candidateRows.map((r) => {
    const sent = getSentimentAvg(r.ticker)
    return {
      ticker: r.ticker,
      exchange: r.exchange,
      stage: r.stage,
      priority: r.priority,
      enrichment: r.fetch_date
        ? ({
            ticker: r.ticker,
            fetch_date: r.fetch_date as string,
            pe_forward: r.pe_forward as number | null,
            eps_growth_1y: r.eps_growth_1y as number | null,
            operating_margin: r.operating_margin as number | null,
            beta_1y: r.beta_1y as number | null,
            price_to_sales: r.price_to_sales as number | null,
            sector: r.sector as string | null,
            region: r.region as string | null,
            source: r.source as string,
            trend_strength: null,
            trend_linearity: null,
            seasonality_strength: null,
            seasonality_stability: null,
            residual_acf1: null,
            spectral_entropy: null,
            is_stationary: null,
            created_at: r.created_at as string,
          })
        : null,
      sentiment_avg: sent.score,
    }
  })

  const shockStocks = detectShockStocks({ candidates, priceDropPct, minMarginPct, maxPSRatio })

  return c.json({ shockStocks, params: { priceDropPct, minMarginPct, maxPSRatio } })
})

// ── GET /api/screenings/shock/html — shock stocks as HTML panel ───────────────

screeningsRouter.get("/shock/html", (c) => {
  const db = DatabaseFactory.get()
  const minMarginPct = parseFloat(c.req.query("margin") ?? "20")
  const maxPSRatio = parseFloat(c.req.query("ps") ?? "5")

  const candidateRows = db
    .query(
      `SELECT w.ticker, w.exchange, w.stage, w.priority, e.*
       FROM watchlist w
       LEFT JOIN watchlist_enrichment e ON w.ticker = e.ticker
       WHERE w.stage != 'acquired'
       ORDER BY w.priority DESC, w.ticker`,
    )
    .all() as Array<
    { ticker: string; exchange: string; stage: string; priority: string } & Record<string, unknown>
  >

  const candidates: CandidateData[] = candidateRows.map((r) => {
    const sent = getSentimentAvg(r.ticker)
    return {
      ticker: r.ticker,
      exchange: r.exchange,
      stage: r.stage,
      priority: r.priority,
      enrichment: r.fetch_date
        ? ({
            ticker: r.ticker,
            fetch_date: r.fetch_date as string,
            pe_forward: r.pe_forward as number | null,
            eps_growth_1y: r.eps_growth_1y as number | null,
            operating_margin: r.operating_margin as number | null,
            beta_1y: r.beta_1y as number | null,
            price_to_sales: r.price_to_sales as number | null,
            sector: r.sector as string | null,
            region: r.region as string | null,
            source: r.source as string,
            trend_strength: null,
            trend_linearity: null,
            seasonality_strength: null,
            seasonality_stability: null,
            residual_acf1: null,
            spectral_entropy: null,
            is_stationary: null,
            created_at: r.created_at as string,
          })
        : null,
      sentiment_avg: sent.score,
    }
  })

  const shockStocks = detectShockStocks({ candidates, priceDropPct: 10, minMarginPct, maxPSRatio })

  const hasResults = shockStocks.length > 0

  return c.html(
    <section class="panel shock-panel" id="shock-panel">
      <div class="shock-header">
        <h4>⚡ Shock Stocks</h4>
        <span class="shock-params">
          margin &gt; {minMarginPct}% | P/S &lt; {maxPSRatio}
        </span>
        {hasResults ? (
          <span class="badge">{shockStocks.length} found</span>
        ) : (
          <span class="badge secondary">none found</span>
        )}
      </div>

      {!hasResults ? (
        <p class="empty-state">
          No shock stocks detected. Ensure enrichment data is populated via{" "}
          <code>trading screen enrich --all</code>.
        </p>
      ) : (
        <table class="screening-table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Stage</th>
              <th>Op. Margin</th>
              <th>P/S</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {shockStocks.map((s) => (
              <tr key={s.ticker}>
                <td class="ticker">{s.ticker}</td>
                <td>
                  <span class={`stage-chip stage-${s.stage}`}>{s.stage}</span>
                </td>
                <td class="metric">
                  {s.enrichment?.operating_margin != null
                    ? `${s.enrichment.operating_margin.toFixed(1)}%`
                    : "—"}
                </td>
                <td class="metric">
                  {s.enrichment?.price_to_sales != null
                    ? s.enrichment.price_to_sales.toFixed(2)
                    : "—"}
                </td>
                <td class="reason">{s.match_reasons[0] ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>,
  )
})

// ── GET /api/screenings/history — recent screening runs ───────────────────────

screeningsRouter.get("/history", (c) => {
  const limit = parseInt(c.req.query("limit") ?? "10", 10)
  const screenings = getRecentScreenings(limit)
  return c.json({ screenings })
})

// ── GET /api/screenings/history/html — screening history as HTML panel ────────

screeningsRouter.get("/history/html", (c) => {
  const limit = parseInt(c.req.query("limit") ?? "10", 10)
  const screenings = getRecentScreenings(limit)

  if (screenings.length === 0) {
    return c.html(
      <section class="panel screening-history-panel" id="screening-history-panel">
        <div class="screening-header">
          <h4>Screening History</h4>
          <span class="badge secondary">empty</span>
        </div>
        <p class="empty-state">No screening runs recorded yet. Run <code>trading screen run</code> to populate history.</p>
      </section>,
    )
  }

  return c.html(
    <section class="panel screening-history-panel" id="screening-history-panel">
      <div class="screening-header">
        <h4>Screening History</h4>
        <span class="badge">{screenings.length} runs</span>
      </div>
      <table class="screening-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Rules</th>
            <th>Matched</th>
            <th>Tickers</th>
          </tr>
        </thead>
        <tbody>
          {screenings.map((s) => (
            <tr key={s.id}>
              <td class="date">{s.run_date}</td>
              <td>{s.rule_count}</td>
              <td class="score">{s.tickers_matched.length}</td>
              <td class="tickers">{s.tickers_matched.slice(0, 6).join(", ")}{s.tickers_matched.length > 6 ? ` +${s.tickers_matched.length - 6}` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>,
  )
})

// ── GET /api/screenings/rules — list screening rules ──────────────────────────

screeningsRouter.get("/rules", (c) => {
  const rules = listScreeningRules()
  return c.json({ rules })
})