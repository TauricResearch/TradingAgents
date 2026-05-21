/**
 * Twelve Data API client — free-tier US equity pricing + forex + crypto.
 *
 * Free tier: 800 calls/day, 8 credits/min. Batch endpoint consumes 1 credit
 * regardless of ticker count. Real-time US stocks, forex, crypto.
 *
 * API key: TWELVEDATA_API_KEY (from Skate or env)
 */

// ── Types ────────────────────────────────────────────────────────────────────

export interface PriceResult {
  ticker: string
  price: number | null
  currency: string
  previousClose: number | null
  dayHigh: number | null
  dayLow: number | null
  volume: number | null
  history: Array<{ date: string; close: number }>
  timestamp: string
}

interface TwelveDataQuote {
  symbol: string
  name?: string
  exchange?: string
  currency?: string
  datetime?: string
  open?: string
  high?: string
  low?: string
  close?: string
  previous_close?: string
  volume?: string
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function getKey(): string | undefined {
  return process.env.TWELVEDATA_API_KEY || undefined
}

function isAvailable(): boolean {
  return !!getKey()
}

/**
 * Twelve Data uses plain tickers (AAPL, MSFT) for US stocks.
 * Non-US tickers need exchange suffix (VWCE.DE → VWCE:XETRA)
 * which requires Grow plan. Free tier = US only.
 */
function isUsTicker(ticker: string): boolean {
  // No suffix = US ticker
  if (!ticker.includes(".") && !ticker.includes("-") && !ticker.includes("=")) return true
  // Crypto (BTC-USD, ETH-EUR)
  if (/^[A-Z0-9]{2,6}-(USD|EUR|USDT)$/.test(ticker)) return false
  // Forex (GBPEUR=X, EURUSD=X)
  if (ticker.endsWith("=X")) return false
  // EU/UK/Asia (.DE, .L, .HK, .T, etc.)
  return false
}

function parseNumber(v: string | undefined | null): number | null {
  if (v == null || v === "") return null
  const n = parseFloat(v)
  return Number.isFinite(n) ? n : null
}

// ── API ─────────────────────────────────────────────────────────────────────

const BASE = "https://api.twelvedata.com"

async function twelveDataFetch(endpoint: string, params: Record<string, string>): Promise<unknown> {
  const key = getKey()
  if (!key) throw new Error("TWELVEDATA_API_KEY not set")

  const url = new URL(`${BASE}${endpoint}`)
  url.searchParams.set("apikey", key)
  for (const [k, v] of Object.entries(params)) {
    url.searchParams.set(k, v)
  }

  const response = await fetch(url.toString(), {
    headers: { Accept: "application/json" },
    signal: AbortSignal.timeout(10_000),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Twelve Data ${response.status}: ${text.slice(0, 200)}`)
  }

  return response.json()
}

// ── Single Ticker ───────────────────────────────────────────────────────────

/**
 * Fetch current price for a single US ticker.
 * Returns null if ticker is non-US (free tier limitation) or lookup fails.
 */
export async function getPrice(ticker: string): Promise<PriceResult | null> {
  if (!isAvailable() || !isUsTicker(ticker)) return null

  try {
    const data = (await twelveDataFetch("/quote", {
      symbol: ticker,
      dp: "2",
    })) as TwelveDataQuote

    // Twelve Data returns { code: 400, message: "..." } on errors
    if ((data as unknown as Record<string, unknown>).code) {
      return null
    }

    return {
      ticker: ticker,
      price: parseNumber(data.close),
      currency: data.currency ?? "USD",
      previousClose: parseNumber(data.previous_close),
      dayHigh: parseNumber(data.high),
      dayLow: parseNumber(data.low),
      volume: parseNumber(data.volume),
      history: [],
      timestamp: new Date().toISOString(),
    }
  } catch {
    return null
  }
}

// ── Batch ────────────────────────────────────────────────────────────────────

/**
 * Fetch prices for multiple US tickers in a single API call.
 * Non-US tickers are silently skipped (returned as null in the map).
 * 1 API credit consumed regardless of ticker count.
 */
export async function getBatchPrices(tickers: string[]): Promise<Map<string, PriceResult | null>> {
  const map = new Map<string, PriceResult | null>()

  if (!isAvailable()) {
    for (const t of tickers) map.set(t, null)
    return map
  }

  const usTickers = tickers.filter(isUsTicker)
  const nonUsTickers = tickers.filter((t) => !isUsTicker(t))

  // Non-US tickers are skipped — caller should use fallback
  for (const t of nonUsTickers) map.set(t, null)

  if (usTickers.length === 0) return map

  try {
    const data = (await twelveDataFetch("/quote", {
      symbol: usTickers.join(","),
      dp: "2",
    })) as TwelveDataQuote | TwelveDataQuote[]

    const quotes = Array.isArray(data) ? data : [data]

    // Build map of symbol → quote
    const quoteMap = new Map<string, TwelveDataQuote>()
    for (const q of quotes) {
      quoteMap.set(q.symbol, q)
    }

    for (const ticker of usTickers) {
      const quote = quoteMap.get(ticker)
      if (!quote || (quote as unknown as Record<string, unknown>).code) {
        map.set(ticker, null)
        continue
      }
      map.set(ticker, {
        ticker,
        price: parseNumber(quote.close),
        currency: quote.currency ?? "USD",
        previousClose: parseNumber(quote.previous_close),
        dayHigh: parseNumber(quote.high),
        dayLow: parseNumber(quote.low),
        volume: parseNumber(quote.volume),
        history: [],
        timestamp: new Date().toISOString(),
      })
    }
  } catch {
    for (const t of usTickers) map.set(t, null)
  }

  return map
}

/**
 * Check if Twelve Data is configured and available.
 */
export function isTwelveDataAvailable(): boolean {
  return isAvailable()
}
