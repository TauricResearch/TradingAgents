/** @jsxImportSource hono/jsx */
import { Hono } from "hono";
import { readdirSync, existsSync, readFileSync, writeFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { renderAnalysisReport } from "../lib/markdown.ts";
import { config } from "dotenv";

// Load .env for OPENROUTER_API_KEY
config();

export const analysesRouter = new Hono();

/** Default results directory: ~/.tradingagents/logs */
function resultsDir(): string {
  return process.env.TRADINGAGENTS_RESULTS_DIR
    ?? join(process.env.HOME ?? "/tmp", ".tradingagents", "logs");
}

/**
 * GET /api/analyses — list all available analyses
 * Returns: [{ ticker, date, path }]
 */
analysesRouter.get("/", (c) => {
  const root = resultsDir();
  if (!existsSync(root)) return c.json([]);

  const analyses: Array<{ ticker: string; date: string }> = [];

  // Scan {root}/{ticker}/TradingAgentsStrategy_logs/full_states_log_{date}.json
  for (const ticker of readdirSync(root)) {
    const logDir = join(root, ticker, "TradingAgentsStrategy_logs");
    if (!existsSync(logDir)) continue;
    for (const file of readdirSync(logDir)) {
      const m = file.match(/^full_states_log_(.+)\.json$/);
      if (m?.[1]) analyses.push({ ticker, date: m[1] });
    }
  }

  // Most recent first
  analyses.sort((a, b) => b.date.localeCompare(a.date));
  return c.json(analyses);
});

/**
 * GET /api/analyses/:ticker/:date — rendered HTML report
 * Content-Type: text/html
 */
analysesRouter.get("/:ticker/:date", (c) => {
  const { ticker, date } = c.req.param();
  const logPath = join(resultsDir(), ticker, "TradingAgentsStrategy_logs", `full_states_log_${date}.json`);

  if (!existsSync(logPath)) {
    return c.text("Analysis not found", 404);
  }

  const raw = readFileSync(logPath, "utf-8");
  const state = JSON.parse(raw) as Record<string, unknown>;
  const html = renderAnalysisReport(state);

  return c.html(`<div class="panel"><div class="report-body">${html}</div></div>`);
});

/**
 * GET /api/analyses/:ticker/:date/json — raw JSON
 */
analysesRouter.get("/:ticker/:date/json", (c) => {
  const { ticker, date } = c.req.param();
  const logPath = join(resultsDir(), ticker, "TradingAgentsStrategy_logs", `full_states_log_${date}.json`);

  if (!existsSync(logPath)) {
    return c.json({ error: "not found" }, 404);
  }

  const raw = readFileSync(logPath, "utf-8");
  return c.json(JSON.parse(raw));
});

/**
 * POST /api/analyses/:ticker/:date/explain — LLM-powered plain-English summary
 * Body: { prompt? } — optional custom prompt
 */
analysesRouter.post("/:ticker/:date/explain", async (c) => {
  const { ticker, date } = c.req.param();
  const logPath = join(resultsDir(), ticker, "TradingAgentsStrategy_logs", `full_states_log_${date}.json`);
  const summaryPath = join(resultsDir(), ticker, "TradingAgentsStrategy_logs", `summary_${date}.json`);

  if (!existsSync(logPath)) {
    return c.json({ error: "Analysis not found", ticker, date }, 404);
  }

  // Return cached summary if it exists
  if (existsSync(summaryPath)) {
    try {
      const cached = JSON.parse(readFileSync(summaryPath, "utf-8"));
      return c.json({ ...cached, _cached: true });
    } catch {
      // Corrupted cache, regenerate
    }
  }

  // Check API key
  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    return c.json({
      error: "OPENROUTER_API_KEY not configured",
      hint: "Add OPENROUTER_API_KEY=sk-or-... to your .env file and restart the server",
    }, 503);
  }

  const raw = readFileSync(logPath, "utf-8");
  let state: Record<string, unknown>;
  try {
    state = JSON.parse(raw);
  } catch (e: unknown) {
    return c.json({ error: "Invalid log file", detail: (e as Error).message }, 500);
  }

  const decision = String(state.final_trade_decision ?? "");

  // Extract agent reports for context
  const reports: Record<string, string> = {};
  for (const [key, value] of Object.entries(state)) {
    if (typeof value === "string" && value.length > 0 && key.endsWith("_report")) {
      reports[key.replace("_report", "")] = value.slice(0, 1000);
    }
  }

  const body = await c.req.json().catch(() => ({}));
  const customPrompt = body.prompt ?? "";

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

Respond with ONLY valid JSON. No markdown, no explanation.`;

  const userPrompt = `Analyse this trading decision for ${ticker} on ${date}.

Decision:
${decision.slice(0, 2000)}

Agent reports:
${JSON.stringify(reports, null, 2).slice(0, 2000)}
${customPrompt ? `\n\nAdditional question: ${customPrompt}` : ""}`;

  let resp: Response;
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
    });
  } catch (e: unknown) {
    return c.json({
      error: "LLM request failed",
      detail: (e as Error).message,
      hint: "Check network connectivity",
    }, 502);
  }

  if (!resp.ok) {
    const errorBody = await resp.text().catch(() => "");
    return c.json({
      error: `LLM API returned ${resp.status}`,
      detail: errorBody.slice(0, 500),
      hint: resp.status === 401 ? "Invalid API key" : resp.status === 429 ? "Rate limited" : "Check API status",
    }, resp.status);
  }

  let data: { choices?: Array<{ message?: { content?: string } }> };
  try {
    data = await resp.json();
  } catch {
    return c.json({ error: "Invalid LLM response", detail: "Could not parse JSON" }, 502);
  }

  const content = data.choices?.[0]?.message?.content ?? "";
  if (!content) {
    return c.json({ error: "Empty LLM response", detail: "No content in response" }, 502);
  }

  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(content);
  } catch {
    // Return raw text if JSON parse fails
    parsed = { plain_english: content };
  }

  // Cache the summary
  try {
    writeFileSync(summaryPath, JSON.stringify(parsed, null, 2), "utf-8");
  } catch {
    // Cache write failure is non-fatal
  }

  return c.json(parsed);
});

/**
 * GET /api/analyses/:ticker/:date/summary — structured card data
 */
analysesRouter.get("/:ticker/:date/summary", (c) => {
  const { ticker, date } = c.req.param();
  const logPath = join(resultsDir(), ticker, "TradingAgentsStrategy_logs", `full_states_log_${date}.json`);

  if (!existsSync(logPath)) {
    return c.json({ error: "not found" }, 404);
  }

  const raw = readFileSync(logPath, "utf-8");
  const state = JSON.parse(raw) as Record<string, unknown>;

  // Extract decision signal
  const decision = String(state.final_trade_decision ?? "");
  const signalMatch = decision.match(/\*\*Rating\*\*:\s*(\w+)/);
  const signal = signalMatch?.[1] ?? extractSignal(decision);

  // Extract confidence from decision text (e.g., "Confidence: 0.75" or similar)
  const confMatch = decision.match(/[Cc]onfidence[:\s]*([0-9.]+)/);
  const confidence = confMatch ? parseFloat(confMatch[1]) : estimateConfidence(decision, signal);

  // Extract executive summary
  const summaryMatch = decision.match(/\*\*Executive Summary\*\*[:\s]*([\s\S]*?)(?=\n\*\*|$)/);
  const summary = summaryMatch?.[1]?.trim().slice(0, 500) ?? decision.slice(0, 500);

  // Extract recommended actions (bullet points from decision)
  const actions = extractActions(decision);

  // Extract agent verdicts (first line of each report)
  const agents: Record<string, string> = {};
  for (const [key, value] of Object.entries(state)) {
    if (typeof value === "string" && value.length > 0 && key.endsWith("_report")) {
      const name = key.replace("_report", "").replace(/_/g, " ");
      const firstLine = value.split("\n")[0]?.slice(0, 200) ?? "";
      const verdictMatch = firstLine.match(/FINAL TRANSACTION PROPOSAL:\s*\*\*(\w+)\*\*/);
      agents[name] = verdictMatch?.[1] ?? firstLine.slice(0, 120);
    }
  }

  // Build confidence sparkline from all analyses for this ticker
  const sparkline = buildConfidenceSparkline(ticker, date);

  return c.json({
    ticker,
    date,
    signal,
    confidence,
    summary,
    actions,
    agents,
    sparkline,
    decision: decision.slice(0, 2000),
  });
});

function extractConfidence(text: string): number | null {
  const confMatch = text.match(/[Cc]onfidence[:\s]*([0-9.]+)/);
  return confMatch ? parseFloat(confMatch[1]) : null;
}

function estimateConfidence(text: string, signal: string): number {
  // Heuristic: stronger signals = higher confidence
  const lower = text.toLowerCase();
  if (lower.includes("strong") || lower.includes("high conviction")) return 0.8;
  if (lower.includes("cautious") || lower.includes("conditional")) return 0.5;
  if (lower.includes("reduce") || lower.includes("trim")) return 0.4;
  if (signal === "Overweight") return 0.7;
  if (signal === "Underweight") return 0.6;
  return 0.5;
}

function extractActions(text: string): Array<{ label: string; text: string }> {
  const items: Array<{ label: string; text: string }> = [];
  const summaryMatch = text.match(/\*\*Executive Summary\*\*[:\s]*([\s\S]*?)(?=\n\*\*|$)/);
  if (!summaryMatch) return items;
  const body = summaryMatch[1].trim();

  // Position sizing
  const sizeMatch = body.match(/(\d+\.?\d*x\s*(?:to|–|-)\s*\d+\.?\d*x\s*benchmark)/i);
  if (sizeMatch) items.push({ label: "Position size", text: sizeMatch[1] });

  // Entry strategy
  const entryMatch = body.match(/(build[^,]+in tranches[^,.]*[,.])/i);
  if (entryMatch) items.push({ label: "Entry", text: entryMatch[1].replace(/[,.]$/, "").trim() });
  const pullbackMatch = body.match(/(prioritizing[^,.]+[,.])/i);
  if (pullbackMatch) items.push({ label: "Strategy", text: pullbackMatch[1].replace(/[,.]$/, "").trim() });

  // Risk levels
  const riskMatch = body.match(/(tighten risk[^,.]+[,.]|(?:stop|invalidation)[^,.]*[,.])/i);
  if (riskMatch) items.push({ label: "Risk control", text: riskMatch[1].replace(/[,.]$/, "").trim() });

  // Time horizon
  const horizonMatch = body.match(/((?:\d+[-–]?\d+\s*(?:month|week|day|year)[^,.]*)|(?:short|medium|long)[- ]?term[^,.]*[,.])/i);
  if (horizonMatch) items.push({ label: "Horizon", text: horizonMatch[1].replace(/[,.]$/, "").trim() });

  // Watch/catalysts
  const watchMatch = body.match(/(reassess if[^,.]+[,.]|monitor[^,.]+[,.]|watch for[^,.]+[,.])/i);
  if (watchMatch) items.push({ label: "Watch for", text: watchMatch[1].replace(/[,.]$/, "").trim() });

  // Fallback: if nothing structured, just return raw summary split by semicolons
  if (items.length === 0) {
    const parts = body.split(/[;,.]/).filter(s => s.trim().length > 20);
    for (const p of parts.slice(0, 4)) {
      items.push({ label: "", text: p.trim() });
    }
  }
  return items.slice(0, 6);
}

function buildConfidenceSparkline(ticker: string, current: string): number[] {
  const root = resultsDir();
  const logDir = join(root, ticker, "TradingAgentsStrategy_logs");
  if (!existsSync(logDir)) return [];

  const values: Array<{ date: string; conf: number }> = [];
  for (const file of readdirSync(logDir)) {
    const m = file.match(/^full_states_log_(.+)\.json$/);
    if (!m?.[1]) continue;
    const date = m[1];
    if (date > current) continue;
    try {
      const raw = readFileSync(join(logDir, file), "utf-8");
      const state = JSON.parse(raw) as Record<string, unknown>;
      const decision = String(state.final_trade_decision ?? "");
      const conf = extractConfidence(decision) ?? estimateConfidence(decision, extractSignal(decision));
      values.push({ date, conf });
    } catch { /* skip */ }
  }
  values.sort((a, b) => a.date.localeCompare(b.date));
  return values.map(v => Math.round(v.conf * 100));
}

function extractSignal(text: string): string {
  const lower = text.toLowerCase();
  if (lower.includes("overweight") || lower.includes("buy")) return "Overweight";
  if (lower.includes("underweight") || lower.includes("sell")) return "Underweight";
  return "Hold";
}
