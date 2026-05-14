#!/usr/bin/env bun

/**
 * Cost-Control AI Proxy (BiFrost-style)
 *
 * A lightweight OpenAI-compatible proxy that routes LLM calls through configured
 * providers (OpenRouter, Ollama, etc.) while logging costs and enforcing spend limits.
 *
 * Usage:
 *   bun run scripts/bifrost-proxy.ts              # start on port 8080
 *   bun run scripts/bifrost-proxy.ts --port 9000  # custom port
 *
 * Routes through:
 *   base_url: http://localhost:8080/v1
 *
 * Environment:
 *   OPENROUTER_API_KEY       - required for OpenRouter
 *   BIFROST_PROVIDER        - openrouter | ollama | direct (default: openrouter)
 *   BIFROST_DRY_RUN         - if "1", log only, don't forward requests
 *   BIFROST_COST_LOG        - path to cost log (default: ~/.tradingagents/bifrost-cost-log.jsonl)
 *   BIFROST_SPEND_LIMIT     - max USD per request (default: 1.00)
 */

import { appendFileSync, existsSync, mkdirSync } from "node:fs"
import { homedir } from "node:os"
import { join } from "node:path"
import { serve } from "@hono/node-server"
import { Hono } from "hono"
import { cors } from "hono/cors"

// ── Pricing (price per 1M tokens: [prompt, completion]) ──────────────────────
const MODEL_PRICING: Record<string, [number, number]> = {
  "deepseek/deepseek-v4-flash": [0.1, 0.3],
  "deepseek/deepseek-v4-pro": [0.4, 0.9],
  "deepseek/deepseek-r1": [0.7, 2.5],
  "deepseek/deepseek-r1-0528": [0.5, 2.2],
  "deepseek/deepseek-chat": [0.3, 0.9],
  "qwen/qwen3-30b-a3b-thinking-2507": [0.1, 0.4],
  "qwen/qwen3-next-80b-a3b-thinking": [0.1, 0.8],
  "qwen/qwen-plus": [0.3, 0.8],
  "openai/gpt-5.4": [2.5, 15.0],
  "openai/gpt-5.4-mini": [0.8, 4.5],
  "openai/gpt-4o-mini": [0.1, 0.6],
  "openai/gpt-4o": [2.5, 10.0],
  "anthropic/claude-3.5-sonnet": [3.0, 15.0],
  "anthropic/claude-3.5-haiku": [0.8, 4.0],
  "google/gemini-2.5-flash-lite": [0.1, 0.4],
  "google/gemini-2.5-flash": [0.3, 2.5],
  "moonshotai/kimi-k2": [0.6, 2.3],
  "moonshotai/kimi-k2-thinking": [0.6, 2.5],
  // Ollama local models — zero cost
  "deepseek-coder-v2:latest": [0, 0],
  "qwen2.5-coder:32b-instruct": [0, 0],
  "llama3.1:8b-instruct": [0, 0],
  "llama3.1:70b-instruct": [0, 0],
}

const DEFAULT_PRICING: [number, number] = [1.0, 5.0]

// ── Config ───────────────────────────────────────────────────────────────────
const CONFIG = {
  port: parseInt(process.env.BIFROST_PORT ?? "8080", 10),
  provider: process.env.BIFROST_PROVIDER ?? "openrouter",
  dryRun: process.env.BIFROST_DRY_RUN === "1",
  costLogPath:
    process.env.BIFROST_COST_LOG ?? join(homedir(), ".tradingagents", "bifrost-cost-log.jsonl"),
  spendLimit: parseFloat(process.env.BIFROST_SPEND_LIMIT ?? "1.00"),
  openRouterKey: process.env.OPENROUTER_API_KEY ?? "",
}

const PROVIDER_ENDPOINTS: Record<string, string> = {
  openrouter: "https://openrouter.ai/api/v1",
  ollama: "http://localhost:11434/v1",
  direct: "https://api.openai.com/v1",
}

// ── Cost Calculation ─────────────────────────────────────────────────────────
function calculateCost(model: string, promptTokens: number, completionTokens: number): number {
  const [promptPrice, completionPrice] = MODEL_PRICING[model] ?? DEFAULT_PRICING
  const cost =
    (promptTokens / 1_000_000) * promptPrice + (completionTokens / 1_000_000) * completionPrice
  return Math.round(cost * 1_000_000) / 1_000_000
}

// ── Cost Logging ─────────────────────────────────────────────────────────────
interface CostLogEntry {
  timestamp: string
  model: string
  provider: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost_usd: number
  latency_ms: number
  status: "success" | "error" | "dry_run"
  cache_hit: boolean
  error?: string
}

function logCost(entry: CostLogEntry): void {
  try {
    const dir = join(CONFIG.costLogPath, "..")
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
    appendFileSync(CONFIG.costLogPath, `${JSON.stringify(entry)}\n`, "utf-8")
  } catch (e) {
    console.error("Failed to write cost log:", e)
  }
}

// ── Proxy Handler ─────────────────────────────────────────────────────────────
// biome-ignore lint/suspicious/noExplicitAny: Hono context uses dynamic any types
async function handleProxy(c: any, body: any, path: string) {
  const model = body.model ?? "unknown"
  const startTime = Date.now()

  // Check spend limit
  const estimatedTokens = body.max_tokens ?? 1024
  const estimatedCost = calculateCost(model, estimatedTokens, estimatedTokens)

  if (estimatedCost > CONFIG.spendLimit) {
    logCost({
      timestamp: new Date().toISOString(),
      model,
      provider: CONFIG.provider,
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
      cost_usd: 0,
      latency_ms: Date.now() - startTime,
      status: "error",
      cache_hit: false,
      error: `Spend limit exceeded: ${estimatedCost} > ${CONFIG.spendLimit}`,
    })
    return c.json(
      {
        error: {
          message: `Spend limit exceeded: estimated cost ${estimatedCost} USD > limit ${CONFIG.spendLimit} USD`,
          type: "spend_limit_exceeded",
          code: 429,
        },
      },
      429,
    )
  }

  // Dry run — log and return mock response
  if (CONFIG.dryRun) {
    logCost({
      timestamp: new Date().toISOString(),
      model,
      provider: CONFIG.provider,
      prompt_tokens: 100,
      completion_tokens: 50,
      total_tokens: 150,
      cost_usd: 0,
      latency_ms: Date.now() - startTime,
      status: "dry_run",
      cache_hit: false,
    })
    return c.json({
      model,
      choices: [
        {
          message: { role: "assistant", content: "[dry-run] Request logged, not forwarded." },
          finish_reason: "stop",
        },
      ],
    })
  }

  // Forward to provider
  const endpoint = PROVIDER_ENDPOINTS[CONFIG.provider] ?? PROVIDER_ENDPOINTS.openrouter
  const url = `${endpoint}${path}`

  const headers: Record<string, string> = { "Content-Type": "application/json" }
  if (CONFIG.provider === "openrouter" && CONFIG.openRouterKey) {
    headers.Authorization = `Bearer ${CONFIG.openRouterKey}`
    headers["HTTP-Referer"] = "https://tradingagents.local"
    headers["X-Title"] = "TradingAgents BiFrost Proxy"
  } else if (CONFIG.provider === "ollama") {
    headers.Authorization = "Bearer ollama"
  }

  try {
    const response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(120_000),
    })

    const latency = Date.now() - startTime
    const data = await response.json()

    let promptTokens = 0,
      completionTokens = 0,
      totalTokens = 0
    if (data.usage) {
      promptTokens = data.usage.prompt_tokens ?? 0
      completionTokens = data.usage.completion_tokens ?? 0
      totalTokens = data.usage.total_tokens ?? 0
    }

    const actualCost = calculateCost(model, promptTokens, completionTokens)

    logCost({
      timestamp: new Date().toISOString(),
      model,
      provider: CONFIG.provider,
      prompt_tokens: promptTokens,
      completion_tokens: completionTokens,
      total_tokens: totalTokens,
      cost_usd: actualCost,
      latency_ms: latency,
      status: response.ok ? "success" : "error",
      cache_hit: false,
      error: response.ok
        ? undefined
        : `HTTP ${response.status}: ${JSON.stringify(data).slice(0, 200)}`,
    })

    return c.json(data, response.status)
  } catch (e) {
    const error = e instanceof Error ? e.message : String(e)
    logCost({
      timestamp: new Date().toISOString(),
      model,
      provider: CONFIG.provider,
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
      cost_usd: 0,
      latency_ms: Date.now() - startTime,
      status: "error",
      cache_hit: false,
      error,
    })
    return c.json({ error: { message: `Proxy error: ${error}`, type: "proxy_error" } }, 502)
  }
}

// ── Hono App ─────────────────────────────────────────────────────────────────
const app = new Hono()
app.use("*", cors())

app.get("/health", (c) =>
  c.json({
    status: "ok",
    provider: CONFIG.provider,
    dry_run: CONFIG.dryRun,
    spend_limit: CONFIG.spendLimit,
  }),
)

app.get("/costs", async (c) => {
  const logPath = CONFIG.costLogPath
  if (!existsSync(logPath)) return c.json({ total_cost: 0, requests: 0 })

  const { readFileSync } = await import("node:fs")
  try {
    const content = readFileSync(logPath, "utf-8")
    const entries = content
      .trim()
      .split("\n")
      .filter(Boolean)
      .map((l) => JSON.parse(l) as CostLogEntry)
    const totalCost = entries.reduce((sum, e) => sum + (e.cost_usd ?? 0), 0)
    const byModel: Record<string, { count: number; cost: number }> = {}
    for (const e of entries) {
      if (!byModel[e.model]) byModel[e.model] = { count: 0, cost: 0 }
      byModel[e.model].count++
      byModel[e.model].cost += e.cost_usd ?? 0
    }
    return c.json({
      total_cost: Math.round(totalCost * 1_000_000) / 1_000_000,
      total_requests: entries.length,
      by_model: byModel,
    })
  } catch {
    return c.json({ total_cost: 0, requests: 0 })
  }
})

// OpenAI-compatible endpoints
app.post("/v1/chat/completions", async (c) => {
  return handleProxy(c, await c.req.json(), "/chat/completions")
})
app.post("/v1/responses", async (c) => {
  return handleProxy(c, await c.req.json(), "/responses")
})

app.get("/v1/models", (c) =>
  c.json({
    object: "list",
    data: Object.keys(MODEL_PRICING).map((id) => ({
      id,
      object: "model",
      created: 1700000000,
      owned_by: "bifrost",
    })),
  }),
)

// ── Startup ─────────────────────────────────────────────────────────────────
const server = serve({ fetch: app.fetch, port: CONFIG.port })

console.log(`
╔═══════════════════════════════════════════════════════════╗
║  BiFrost Cost-Control Proxy                               ║
╠═══════════════════════════════════════════════════════════╣
║  Listening:  http://localhost:${String(CONFIG.port).padEnd(32)}║
║  Provider:   ${CONFIG.provider.padEnd(50)}║
║  Dry run:    ${String(CONFIG.dryRun).padEnd(50)}║
║  Spend limit: $${CONFIG.spendLimit.toFixed(2)} / request                        ║
╚═══════════════════════════════════════════════════════════╝
`)

process.on("SIGINT", () => {
  server.close()
  process.exit(0)
})
process.on("SIGTERM", () => {
  server.close()
  process.exit(0)
})
