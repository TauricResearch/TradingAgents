/** @jsxImportSource hono/jsx */
import { Hono } from "hono";
import type { Context } from "hono";
import { serveStatic } from "hono/bun";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { DatabaseFactory } from "./lib/db.ts";
import { portfolioRouter } from "./routes/portfolio.ts";
import { analysisRouter } from "./routes/analysis.ts";
import { signalsRouter } from "./routes/signals.ts";
import { pricesRouter } from "./routes/prices.ts";
import { analysesRouter } from "./routes/analyses.ts";
import { Layout } from "./views/layout.tsx";
import { PortfolioView } from "./views/portfolio.tsx";
import { AnalysisView } from "./views/analysis.tsx";
import { SignalsView } from "./views/signals.tsx";
import { HistoryView } from "./views/history.tsx";
import { DatatypeTestView } from "./views/datatype-test.tsx";

const app = new Hono();

// ── Lifecycle ──────────────────────────────────────────────

const DB_PATH = process.env.PORTFOLIO_DB ?? "./portfolio.db";

DatabaseFactory.connect(DB_PATH);

// Load schema on first start (CREATE TABLE IF NOT EXISTS is safe)
const schemaPath = join(import.meta.dir, "lib", "schema.sql");
const schema = readFileSync(schemaPath, "utf-8");
DatabaseFactory.get().exec(schema);

app.get("/health", (c) => {
  return c.json({
    status: "ok",
    db: DatabaseFactory.isConnected(),
    path: DatabaseFactory.path,
  });
});

// ── Pages (JSX SSR) ──────────────────────────────────────

function pageOrPartial(c: Context, view: JSX.Element): Response {
  const isHtmx = c.req.header("HX-Request") === "true";
  return c.html(isHtmx ? view : <Layout>{view}</Layout>);
}

app.get("/", (c) => c.html(<Layout><PortfolioView /></Layout>));
app.get("/portfolio", (c) => pageOrPartial(c, <PortfolioView />));
app.get("/analyze", (c) => pageOrPartial(c, <AnalysisView />));
app.get("/signals", (c) => pageOrPartial(c, <SignalsView />));
app.get("/history", (c) => pageOrPartial(c, <HistoryView />));
app.get("/test/datatype", (c) => pageOrPartial(c, <DatatypeTestView />));

// ── Static (serve only from static/ directory, not source files) ──

app.get("/static/*", serveStatic({ root: "./server/static" }));

// ── API routes ─────────────────────────────────────────────

app.route("/api/positions", portfolioRouter);
app.route("/api/analyze", analysisRouter);
app.route("/api/signals", signalsRouter);
app.route("/api/prices", pricesRouter);
app.route("/api/analyses", analysesRouter);

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
