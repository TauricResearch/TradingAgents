/** @jsxImportSource hono/jsx */
import { Hono } from "hono";
import type { Context } from "hono";
import type { JSX } from "hono/jsx";
import { serveStatic } from "hono/bun";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { DatabaseFactory } from "./lib/db.ts";
import { portfolioRouter } from "./routes/portfolio.ts";
import { analysisRouter } from "./routes/analysis.ts";
import { signalsRouter } from "./routes/signals.ts";
import { pricesRouter } from "./routes/prices.ts";
import { analysesRouter } from "./routes/analyses.ts";
import { holdingsRouter } from "./routes/holdings.ts";
import { exitsRouter } from "./routes/exits.ts";
import { prospectsRouter } from "./routes/prospects.ts";
import { governanceRouter } from "./routes/governance.ts";
import { benchmarkRouter } from "./routes/benchmark.ts";
import { feedbackRouter } from "./routes/feedback.ts";
import { workflowRouter } from "./routes/workflow.ts";
import { Layout } from "./views/layout.tsx";
import { PortfolioView } from "./views/portfolio.tsx";
import { AnalysisView } from "./views/analysis.tsx";
import { SignalsView } from "./views/signals.tsx";
import { HistoryView } from "./views/history.tsx";
import { HoldingsView } from "./views/holdings.tsx";
import { ExitsView } from "./views/exits.tsx";
import { ProspectsView } from "./views/prospects.tsx";
import { GovernanceView } from "./views/governance.tsx";
import { BenchmarkView } from "./views/benchmark.tsx";
import { FeedbackView } from "./views/feedback.tsx";
import { AboutView } from "./views/about.tsx";
import { WorkflowView } from "./views/workflow.tsx";
import { DatatypeTestView } from "./views/datatype-test.tsx";

const app = new Hono();

// ── Lifecycle ──────────────────────────────────────────────

const DB_PATH = process.env.PORTFOLIO_DB ?? "./portfolio.db";

DatabaseFactory.connect(DB_PATH);

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

app.get("/health", (c) => {
  return c.json({
    status: "ok",
    db: DatabaseFactory.isConnected(),
    path: DatabaseFactory.path,
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
  const layout = String(<Layout>{view}</Layout>);
  return renderHtml(layout);
}

app.get("/", (c) => {
  const layout = String(<Layout><PortfolioView /></Layout>);
  return renderHtml(layout);
});
app.get("/portfolio", (c) => pageOrPartial(c, <PortfolioView />));
app.get("/workflow", (c) => pageOrPartial(c, <WorkflowView />));
app.get("/analyze", (c) => pageOrPartial(c, <AnalysisView />));
app.get("/signals", (c) => pageOrPartial(c, <SignalsView />));
app.get("/history", (c) => pageOrPartial(c, <HistoryView />));
app.get("/holdings", (c) => pageOrPartial(c, <HoldingsView />));
app.get("/exits", (c) => pageOrPartial(c, <ExitsView />));
app.get("/prospects", (c) => pageOrPartial(c, <ProspectsView />));
app.get("/governance", (c) => pageOrPartial(c, <GovernanceView />));
app.get("/benchmark", (c) => pageOrPartial(c, <BenchmarkView />));
app.get("/feedback", (c) => pageOrPartial(c, <FeedbackView />));
app.get("/about", (c) => pageOrPartial(c, <AboutView />));
app.get("/test/datatype", (c) => pageOrPartial(c, <DatatypeTestView />));

// ── Static (serve only from static/ directory, not source files) ──

app.get("/static/*", serveStatic({ root: "./server" }));

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

// ── Portfolio summary (P&L in GBP) ─────────────────────────
import { handlePortfolioSummary } from "./routes/portfolio.ts";
app.get("/api/portfolio/summary", handlePortfolioSummary);

// ── Start ──────────────────────────────────────────────────

const port = parseInt(process.env.PORT ?? "3000", 10);
console.log(`DB connected: ${DatabaseFactory.path}`);
console.log(`Listening on :${port}`);

// Graceful shutdown: close DB on SIGINT/SIGTERM
for (const sig of ["SIGINT", "SIGTERM"] as const) {
  process.on(sig, () => {
    console.log(`\n${sig} received, closing DB…`);
    try { DatabaseFactory.close(); } catch { /* ignore */ }
    process.exit(0);
  });
}

export default {
  fetch: app.fetch,
  port,
  idleTimeout: 240, // 4 minutes for long-running analyses
};
