/** Filesystem-based analysis routes: listing, report rendering, LLM summary. */
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { Hono } from "hono"
import type { ContentfulStatusCode } from "hono/utils/http-status"
import { renderAnalysisReport } from "../lib/markdown.ts"
import { cfg } from "../lib/settings.ts"
import {
  buildConfidenceSparkline,
  estimateConfidence,
  extractActions,
  extractSignal,
  resultsDir,
} from "./analyses-common.ts"

export const analysesFsRouter = new Hono()

/**
 * GET /api/analyses — list all available analyses from filesystem.
 * Returns: [{ ticker, date }]
 */
analysesFsRouter.get("/", (c) => {
  const root = resultsDir()
  if (!existsSync(root)) return c.json([])

  const analyses: Array<{ ticker: string; date: string }> = []

  for (const ticker of readdirSync(root)) {
    const logDir = join(root, ticker, "TradingAgentsStrategy_logs")
    if (!existsSync(logDir)) continue
    for (const file of readdirSync(logDir)) {
      const m = file.match(/^full_states_log_(.+)\.json$/)
      if (m?.[1]) analyses.push({ ticker, date: m[1] })
    }
  }

  analyses.sort((a, b) => b.date.localeCompare(a.date))
  return c.json(analyses)
})

/**
 * GET /api/analyses/:ticker/:date — rendered HTML report from filesystem.
 */
analysesFsRouter.get("/:ticker/:date", (c) => {
  const { ticker, date } = c.req.param()
  const logPath = join(
    resultsDir(),
    ticker,
    "TradingAgentsStrategy_logs",
    `full_states_log_${date}.json`,
  )

  if (!existsSync(logPath)) {
    return c.json({ error: "Analysis not found" }, 404)
  }

  const raw = readFileSync(logPath, "utf-8")
  const state = JSON.parse(raw) as Record<string, unknown>
  const html = renderAnalysisReport(state)

  return c.html(`<div class="panel"><div class="report-body">${html}</div></div>`)
})

/**
 * GET /api/analyses/:ticker/:date/json — raw JSON from filesystem.
 */
analysesFsRouter.get("/:ticker/:date/json", (c) => {
  const { ticker, date } = c.req.param()
  const logPath = join(
    resultsDir(),
    ticker,
    "TradingAgentsStrategy_logs",
    `full_states_log_${date}.json`,
  )

  if (!existsSync(logPath)) {
    return c.json({ error: "not found" }, 404)
  }

  const raw = readFileSync(logPath, "utf-8")
  return c.json(JSON.parse(raw))
})

/**
 * POST /api/analyses/:ticker/:date/explain — LLM-powered plain-English summary.
 */
analysesFsRouter.post("/:ticker/:date/explain", async (c) => {
  const { ticker, date } = c.req.param()
  const logPath = join(
    resultsDir(),
    ticker,
    "TradingAgentsStrategy_logs",
    `full_states_log_${date}.json`,
  )
  const summaryPath = join(
    resultsDir(),
    ticker,
    "TradingAgentsStrategy_logs",
    `summary_${date}.json`,
  )

  if (!existsSync(logPath)) {
    return c.json({ error: "Analysis not found", ticker, date }, 404)
  }

  if (existsSync(summaryPath)) {
    try {
      const cached = JSON.parse(readFileSync(summaryPath, "utf-8"))
      return c.json({ ...cached, _cached: true })
    } catch {
      /* corrupted cache, regenerate */
    }
  }

  const apiKey = cfg.app.openRouterApiKey
  if (!apiKey) {
    return c.json(
      {
        error: "OPENROUTER_API_KEY not configured",
        hint: "Add OPENROUTER_API_KEY=sk-or-... to your .env file and restart the server",
      },
      503,
    )
  }

  let state: Record<string, unknown>
  try {
    const raw = readFileSync(logPath, "utf-8")
    state = JSON.parse(raw)
  } catch (e: unknown) {
    return c.json({ error: "Invalid log file", detail: (e as Error).message }, 500)
  }

  const decision = String(state.final_trade_decision ?? "")

  const reports: Record<string, string> = {}
  for (const [key, value] of Object.entries(state)) {
    if (typeof value === "string" && value.length > 0 && key.endsWith("_report")) {
      reports[key.replace("_report", "")] = value.slice(0, 1000)
    }
  }

  const body = await c.req.json().catch(() => ({}))
  const customPrompt = body.prompt ?? ""

  const systemPrompt = `You are a financial analyst explaining trading decisions in plain English.
Given an analysis decision, extract these fields as JSON:
- signal: the recommendation (Buy/Hold/Sell/Overweight/Underweight)
- confidence: 0-1 number
- position_size: recommended position sizing
- entry_strategy: how and when to enter the position
- risk_management: stop losses, invalidation levels, risk controls
- time_horizon: expected holding period
- catalysts: what events or conditions to monitor
- risks: key risk factors
- plain_english: a 2-3 sentence explanation of what this means for an investor

Respond with ONLY valid JSON. No markdown, no explanation.`

  const userPrompt = `Analyse this trading decision for ${ticker} on ${date}.

Decision:
${decision.slice(0, 2000)}

Agent reports:
${JSON.stringify(reports, null, 2).slice(0, 2000)}
${customPrompt ? `\n\nAdditional question: ${customPrompt}` : ""}`

  let resp: Response
  try {
    resp = await fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: "openai/gpt-5.4-mini",
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: userPrompt },
        ],
        temperature: 0.3,
        max_tokens: 800,
      }),
    })
  } catch (e: unknown) {
    return c.json({ error: "LLM request failed", detail: (e as Error).message }, 502)
  }

  if (!resp.ok) {
    const errorBody = await resp.text().catch(() => "")
    return c.json(
      {
        error: `LLM API returned ${resp.status}`,
        detail: errorBody.slice(0, 500),
        hint:
          resp.status === 401
            ? "Invalid API key"
            : resp.status === 429
              ? "Rate limited"
              : "Check API status",
      },
      resp.status as ContentfulStatusCode,
    )
  }

  let data: { choices?: Array<{ message?: { content?: string } }> }
  try {
    data = await resp.json()
  } catch {
    return c.json({ error: "Invalid LLM response", detail: "Could not parse JSON" }, 502)
  }

  const content = data.choices?.[0]?.message?.content ?? ""
  if (!content) {
    return c.json({ error: "Empty LLM response" }, 502)
  }

  let parsed: Record<string, unknown>
  try {
    parsed = JSON.parse(content)
  } catch {
    parsed = { plain_english: content }
  }

  try {
    writeFileSync(summaryPath, JSON.stringify(parsed, null, 2), "utf-8")
  } catch {
    /* cache write failure is non-fatal */
  }

  return c.json(parsed)
})

/**
 * GET /api/analyses/:ticker/:date/summary — structured card data.
 */
analysesFsRouter.get("/:ticker/:date/summary", (c) => {
  const { ticker, date } = c.req.param()
  const logPath = join(
    resultsDir(),
    ticker,
    "TradingAgentsStrategy_logs",
    `full_states_log_${date}.json`,
  )

  if (!existsSync(logPath)) {
    return c.json({ error: "not found" }, 404)
  }

  const raw = readFileSync(logPath, "utf-8")
  const state = JSON.parse(raw) as Record<string, unknown>

  const decision = String(state.final_trade_decision ?? "")
  const signalMatch = decision.match(/\*\*Rating\*\*:\s*(\w+)/)
  const signal = signalMatch?.[1] ?? extractSignal(decision)

  const confMatch = decision.match(/[Cc]onfidence[:\s]*([0-9.]+)/)
  const confidence = confMatch?.[1]
    ? parseFloat(confMatch[1])
    : estimateConfidence(decision, signal)

  const summaryMatch = decision.match(/\*\*Executive Summary\*\*[:\s]*([\s\S]*?)(?=\n\*\*|$)/)
  const summary = summaryMatch?.[1]?.trim().slice(0, 500) ?? decision.slice(0, 500)

  const actions = extractActions(decision)

  const agents: Record<string, string> = {}
  for (const [key, value] of Object.entries(state)) {
    if (typeof value === "string" && value.length > 0 && key.endsWith("_report")) {
      const name = key.replace("_report", "").replace(/_/g, " ")
      const firstLine = value.split("\n")[0]?.slice(0, 200) ?? ""
      const verdictMatch = firstLine.match(/FINAL TRANSACTION PROPOSAL:\s*\*\*(\w+)\*\*/)
      agents[name] = verdictMatch?.[1] ?? firstLine.slice(0, 120)
    }
  }

  const sparkline = buildConfidenceSparkline(ticker, date)

  return c.json({
    ticker,
    date,
    signal,
    confidence,
    summary,
    keyPoints: actions,
    agents,
    sparkline,
    decision: decision.slice(0, 2000),
  })
})
