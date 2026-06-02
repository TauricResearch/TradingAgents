/**
 * Dashboard server entry — Hono app with all route routers mounted.
 * Serves HTMX + server-rendered HTML on port 3000 (TA_DASHBOARD_PORT override).
 */

/** @jsxImportSource hono/jsx */
import { Hono } from "hono";
import type { MiddlewareHandler } from "hono/types";
import { logger } from "@lib/logger";
import { createRequestLogger } from "@lib/request-logger";

// Extend Context to include request logger
declare module "hono" {
  interface ContextVariableMap {
    requestLogger: ReturnType<typeof createRequestLogger>;
  }
}

// Request logging middleware
const requestLoggerMiddleware: MiddlewareHandler = async (c, next) => {
  const requestId = c.req.header("X-Request-ID") ?? crypto.randomUUID();
  const start = Date.now();
  const reqLogger = createRequestLogger(requestId, {
    method: c.req.method,
    path: c.req.path,
  });

  c.set("requestLogger", reqLogger);

  reqLogger.info({ userAgent: c.req.header("User-Agent") }, "Request started");

  await next();

  const duration = Date.now() - start;
  reqLogger.info(
    { status: c.res.status, duration },
    "Request completed",
  );
};

import type { Context } from "hono";
import type { JSX } from "hono/jsx";
import { serveStatic } from "hono/bun";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { DatabaseFactory } from "@lib/db"
import { cfg } from "@lib/settings"
import { portfolioRouter } from "./routes/portfolio.tsx";
import { analysisRouter } from "./routes/analysis.ts";
import { signalsRouter } from "./routes/signals.tsx";
import { pricesRouter } from "./routes/prices.ts";
import { analysesRouter } from "./routes/analyses/index.ts";
import { holdingsRouter } from "./routes/holdings.tsx";
import { exitsRouter } from "./routes/exits.tsx";
import { prospectsRouter } from "./routes/prospects.tsx";
import { governanceRouter } from "./routes/governance.tsx";
import { benchmarkRouter } from "./routes/benchmark.tsx";
import { feedbackRouter } from "./routes/feedback.tsx";
import { workflowRouter } from "./routes/workflow.tsx";
import { intelligenceRouter } from "./routes/portfolio-intelligence.tsx";
import { portfolioBalanceRouter } from "./routes/portfolio-balance.ts";
import { tradePlanRouter } from "./routes/trade-plan.tsx";
import labCurrencyRouter from "./routes/lab-currency.tsx";
import { alertsRouter } from "./routes/alerts.tsx";
import { explorer } from "./routes/explorer.tsx"
import { stocks } from "./routes/stocks.tsx"
import { screeningsRouter } from "./routes/screenings.tsx";
import { AlertsView } from "./views/alerts-view.tsx";
import { Layout } from "./views/layout.tsx";
import { PortfolioView } from "./views/portfolio.tsx";
import { AnalysisView } from "./views/analysis.tsx";
import { SignalsView } from "./views/signals.tsx";
import { HistoryView } from "./views/history.tsx";
import { HoldingsPage } from "./views/holdings.tsx";
import { ExitsView } from "./views/exits.tsx";
import { ProspectsView } from "./views/prospects.tsx";
import { GovernanceView } from "./views/governance.tsx";
import { BenchmarkView } from "./views/benchmark.tsx";
import { FeedbackView } from "./views/feedback.tsx";
import { AboutView } from "./views/about.tsx";
import { WorkflowView } from "./views/workflow.tsx";
import { ScreeningsView } from "./views/screenings-view.tsx";
import { IntelligenceView } from "./views/intelligence.tsx";

import { DatatypeTestView } from "./views/datatype-test.tsx"

const app = new Hono();

// Apply request logging middleware to API routes only
app.use("/api/*", requestLoggerMiddleware)

// ── Lifecycle ──────────────────────────────────────────────

// TEST_MODE=1 → use test_portfolio.db instead of portfolio.db
// TEST_PORTFOLIO_DB env var overrides the test DB path
if (cfg.isTestMode) {
  logger.info({ db: cfg.portfolio.db }, "[TEST MODE] Using DB");
}

DatabaseFactory.connect(cfg.portfolio.db);

// Load schema on first start (CREATE TABLE IF NOT EXISTS is safe)
const schemaPath = join(import.meta.dir, "lib", "schema.sql");
const schema = readFileSync(schemaPath, "utf-8");
DatabaseFactory.get().exec(schema);

// Migration: add stage column to watchlist if missing
try {
  DatabaseFactory.get().exec(
    "ALTER TABLE watchlist ADD COLUMN stage TEXT DEFAULT 'researching' CHECK(stage IN ('researching', 'analyzed', 'candidate', 'approved', 'acquired'))",
  );
} catch {
  // Column already exists — safe to ignore
}

// Migration: add fair_value column to watchlist if missing
try {
  DatabaseFactory.get().exec("ALTER TABLE watchlist ADD COLUMN fair_value REAL");
} catch {
  // Column already exists — safe to ignore
}

// Migration: add max_position_gbp column to watchlist if missing
try {
  DatabaseFactory.get().exec("ALTER TABLE watchlist ADD COLUMN max_position_gbp REAL");
} catch {
  // Column already exists — safe to ignore
}

// Migration: add account_id column to positions if missing
try {
  DatabaseFactory.get().exec(
    "ALTER TABLE positions ADD COLUMN account_id TEXT REFERENCES accounts(id)",
  );
} catch {
  // Column already exists — safe to ignore
}

// Migration: add positions account index if missing
try {
  DatabaseFactory.get().exec("CREATE INDEX idx_positions_account ON positions(account_id)");
} catch {
  // Index already exists — safe to ignore
}

// Migration: add research_doc column to watchlist if missing
try {
  DatabaseFactory.get().exec("ALTER TABLE watchlist ADD COLUMN research_doc TEXT");
} catch {
  // Column already exists — safe to ignore
}

// Migration: add last_research_update column to watchlist if missing
try {
  DatabaseFactory.get().exec("ALTER TABLE watchlist ADD COLUMN last_research_update TEXT");
} catch {
  // Column already exists — safe to ignore
}

app.get("/health", (c) => {
  return c.json({
    status: "ok",
    db: DatabaseFactory.isConnected(),
    path: DatabaseFactory.path,
    testMode: cfg.isTestMode,
  });
});

// ── Pages (JSX SSR) ──────────────────────────────────────

function renderHtml(html: string): Response {
  return new Response(`<!DOCTYPE html>\n${html}`, {
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function pageOrPartial(c: Context, view: any): Response | Promise<Response> {
  const isHtmx = c.req.header("HX-Request") === "true";
  if (isHtmx) return c.html(view);
  // Hono c.html() doesn't emit <!DOCTYPE html> — causes Quirks Mode.
  // Render the Layout through JSX, then prepend DOCTYPE manually.
  const layout = String(<Layout testMode={cfg.isTestMode}>{view}</Layout>);
  return renderHtml(layout);
}

app.get("/", (c) => {
  const layout = String(<Layout testMode={cfg.isTestMode}><PortfolioView /></Layout>);
  return renderHtml(layout);
});
app.get("/portfolio", (c) => pageOrPartial(c, <PortfolioView />));
app.get("/intelligence", (c) => pageOrPartial(c, <IntelligenceView />));
app.get("/workflow", (c) => pageOrPartial(c, <WorkflowView />));
app.get("/analyze", (c) => pageOrPartial(c, <AnalysisView />));
app.get("/signals", (c) => pageOrPartial(c, <SignalsView />));
app.get("/history", (c) => pageOrPartial(c, <HistoryView />));
app.get("/holdings", (c) => pageOrPartial(c, <HoldingsPage holdingsData={{ holdings: [], platforms: [], cash: [] }} positionsData={{ positions: [] }} />));
app.get("/exits", (c) => pageOrPartial(c, <ExitsView />));
app.get("/prospects", (c) => pageOrPartial(c, <ProspectsView />));
app.get("/governance", (c) => pageOrPartial(c, <GovernanceView />));
app.get("/benchmark", (c) => pageOrPartial(c, <BenchmarkView />));
app.get("/feedback", (c) => pageOrPartial(c, <FeedbackView />));
app.get("/alerts", (c) => pageOrPartial(c, <AlertsView />));
app.get("/about", (c) => pageOrPartial(c, <AboutView />));
app.get("/test/datatype", (c) => pageOrPartial(c, <DatatypeTestView />));
app.get("/screenings", (c) => pageOrPartial(c, <ScreeningsView />));
app.route("/explorer", explorer);
app.route("/stocks", stocks);
app.route("/lab/currency", labCurrencyRouter);

// ── Static (serve only from static/ directory, not source files) ──

const staticDir = resolve(import.meta.dir, "static");

app.use("/static/*", serveStatic({
  root: staticDir,
  rewriteRequestPath: (path) => path.replace(/^\/static/, ""),
  onFound: (_path, c) => {
    c.header("Cache-Control", "public, max-age=31536000, immutable");
  },
}));

// ── API routes ─────────────────────────────────────────────

app.route("/api/positions", portfolioRouter);
app.route("/api/analyze", analysisRouter);
app.route("/api/signals", signalsRouter);
app.route("/api/prices", pricesRouter);
app.route("/api/analyses", analysesRouter);
app.route("/api/holdings", holdingsRouter);
app.route("/api/positions/exits", exitsRouter);
app.route("/api/prospects", prospectsRouter);
app.route("/api/governance", governanceRouter);
app.route("/api/benchmark", benchmarkRouter);
app.route("/api/feedback", feedbackRouter);
app.route("/api/workflow", workflowRouter);
app.route("/api/portfolio/intelligence", intelligenceRouter);
app.route("/api/portfolio/balance", portfolioBalanceRouter);
app.route("/api/trade-plan", tradePlanRouter);
app.route("/api/alerts", alertsRouter);
app.route("/api/screenings", screeningsRouter);

// ── Portfolio summary (P&L in GBP) ─────────────────────────
import { handlePortfolioSummary, handlePortfolioSummaryHtml } from "./routes/portfolio.tsx";
app.get("/api/portfolio/summary", handlePortfolioSummary);
app.get("/api/portfolio/summary/html", handlePortfolioSummaryHtml);

// ── Start ──────────────────────────────────────────────────

const port = cfg.app.dashboardPort;
logger.info({ dbPath: DatabaseFactory.path }, "DB connected");
logger.info({ port }, "Server listening");

// Graceful shutdown: close DB on SIGINT/SIGTERM
for (const sig of ["SIGINT", "SIGTERM"] as const) {
  process.on(sig, () => {
    logger.info({ signal: sig }, "Received shutdown signal, closing DB");
    try { DatabaseFactory.close(); } catch { /* ignore */ }
    process.exit(0);
  });
}

export default {
  fetch: app.fetch,
  port,
  idleTimeout: 240, // 4 minutes for long-running analyses
};
