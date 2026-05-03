import { spawn } from "node:child_process"
import { dirname, join } from "node:path"
import { Hono } from "hono"

export const pricesRouter = new Hono()

/**
 * Resolve the project root (same logic as analysis.ts).
 */
function findProjectRoot(): string {
  if (process.env.TA_ROOT) return process.env.TA_ROOT
  const projectRoot = dirname(dirname(import.meta.dir))
  if (projectRoot.includes("TradingAgents")) return projectRoot
  return projectRoot
}

/**
 * GET /api/prices/:ticker — current price via yfinance subprocess
 *
 * Spawns a short Python script that uses yfinance to fetch:
 *   - current price (regular market price)
 *   - currency
 *   - recent price history (for sparklines)
 *
 * Returns 503 with retry hint if yfinance lookup fails.
 */
pricesRouter.get("/:ticker", async (c) => {
  const ticker = c.req.param("ticker")

  const root = findProjectRoot()
  const script = join(root, "scripts", "get_price.py")

  const result = await runPython(script, ticker)

  if (!result) {
    return c.json(
      {
        error: "Price lookup failed",
        ticker,
        hint: "Check that yfinance is installed: uv pip install yfinance",
        timestamp: new Date().toISOString(),
      },
      503,
    )
  }

  return c.json(result)
})

/**
 * GET /api/prices/batch — fetch prices for multiple tickers
 *
 * Body: { tickers: string[] }
 * Returns array of price objects. Individual failures are non-fatal.
 */
pricesRouter.post("/batch", async (c) => {
  const body = await c.req.json()
  const tickers: string[] = body?.tickers ?? []

  if (tickers.length === 0) {
    return c.json({ error: "No tickers provided" }, 400)
  }

  // Limit to prevent abuse
  if (tickers.length > 50) {
    return c.json({ error: "Max 50 tickers per batch" }, 400)
  }

  const results = await Promise.all(
    tickers.map(async (t) => {
      const root = findProjectRoot()
      const script = join(root, "scripts", "get_price.py")
      return (await runPython(script, t)) ?? { ticker: t, price: null, error: "lookup failed" }
    }),
  )

  return c.json({ prices: results })
})

// ── Helpers ──────────────────────────────────────────────────────────

interface PriceResult {
  ticker: string
  price: number | null
  currency: string
  previousClose: number | null
  dayHigh: number | null
  dayLow: number | null
  volume: number | null
  history: { date: string; close: number }[]
  timestamp: string
}

function runPython(script: string, ticker: string): Promise<PriceResult | null> {
  return new Promise((resolve) => {
    const child = spawn("python3", [script, ticker], {
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
      timeout: 15_000, // 15s max
    })

    let stdout = ""
    let _stderr = ""

    child.stdout.on("data", (d: Buffer) => {
      stdout += d.toString()
    })
    child.stderr.on("data", (d: Buffer) => {
      _stderr += d.toString()
    })

    child.on("close", (code) => {
      if (code !== 0) {
        resolve(null)
        return
      }

      try {
        const data = JSON.parse(stdout.trim())
        resolve({
          ticker: data.ticker ?? ticker,
          price: data.price ?? null,
          currency: data.currency ?? "USD",
          previousClose: data.previousClose ?? null,
          dayHigh: data.dayHigh ?? null,
          dayLow: data.dayLow ?? null,
          volume: data.volume ?? null,
          history: data.history ?? [],
          timestamp: new Date().toISOString(),
        })
      } catch {
        resolve(null)
      }
    })

    child.on("error", () => resolve(null))
  })
}
