/** @jsxImportSource hono/jsx */
import { Hono } from "hono";
import { readdirSync, existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { renderAnalysisReport } from "../lib/markdown.ts";

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
