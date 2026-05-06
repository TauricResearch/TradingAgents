/** @jsxImportSource hono/jsx */
import { Hono } from "hono"
import {
  createSignal,
  fetchSignalsWithHistory,
  getDistinctPlatforms,
  getDistinctTickers,
  getSignals,
  getSignalsForTicker,
  type Signal,
} from "../lib/signals-data.ts"
import { SignalsViewHtml } from "../views/signals-view.tsx"

export const signalsRouter = new Hono()

/** GET /api/signals — list all signals, optionally filter by ticker or platform */
signalsRouter.get("/", (c) => {
  const ticker = c.req.query("ticker")
  const platform = c.req.query("platform")
  const rows = getSignals(ticker || undefined, platform || undefined)
  return c.json(rows)
})

/** GET /api/signals/table — signals with price history for sparklines */
signalsRouter.get("/table", async (c) => {
  const { signals, priceData } = await fetchSignalsWithHistory(
    c.req.query("ticker") || undefined,
    c.req.query("platform") || undefined,
  )
  const enriched = signals.map((s) => ({
    ...s,
    price_history: priceData.get(s.ticker) ?? null,
  }))
  return c.json(enriched)
})

/** GET /api/signals/view/html — full signals view as HTML for HTMX */
signalsRouter.get("/view/html", async (c) => {
  try {
    const platform = c.req.query("platform") || ""
    const ticker = c.req.query("ticker") || ""
    const { signals, priceData } = await fetchSignalsWithHistory(
      ticker || undefined,
      platform || undefined,
    )

    const allPlatforms = getDistinctPlatforms()
    const allTickers = getDistinctTickers()

    return c.html(
      <SignalsViewHtml
        signals={signals}
        priceData={priceData}
        allPlatforms={allPlatforms}
        allTickers={allTickers}
        selectedPlatform={platform}
        selectedTicker={ticker}
      />,
    )
  } catch (e: unknown) {
    return c.html(
      <div class="error-card">
        <strong>Signals error</strong>
        <br />
        {(e as Error).message}
      </div>,
      500,
    )
  }
})

/** GET /api/signals/:ticker — signal timeline for a specific ticker */
signalsRouter.get("/:ticker", (c) => {
  const ticker = c.req.param("ticker")
  const rows = getSignalsForTicker(ticker)
  return c.json(rows)
})

/** POST /api/signals — record a new signal */
signalsRouter.post("/", async (c) => {
  const body = await c.req.json()
  const { ticker, date, signal, reasoning, confidence, platform } = body

  if (!ticker || !signal) {
    return c.json({ error: "ticker and signal are required" }, 400)
  }

  try {
    const result = createSignal({ ticker, date, signal, reasoning, confidence, platform })
    return c.json(result, 201)
  } catch (e: unknown) {
    return c.json({ error: (e as Error).message }, 400)
  }
})
