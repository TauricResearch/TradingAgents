import { Hono } from "hono";
import { serveStatic } from "hono/bun";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { DatabaseFactory } from "./lib/db.ts";
import { portfolioRouter } from "./routes/portfolio.ts";
import { analysisRouter } from "./routes/analysis.ts";
import { signalsRouter } from "./routes/signals.ts";
import { pricesRouter } from "./routes/prices.ts";

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

// ── Pages ──────────────────────────────────────────────────

app.get("/", (c) => {
  return c.html(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TradingAgents Dashboard</title>
  <link rel="stylesheet" href="/static/style.css">
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
</head>
<body>
  <header>
    <h1>TradingAgents</h1>
    <nav>
      <a href="/portfolio">Portfolio</a>
      <a href="/analyze">Analysis</a>
      <a href="/signals">Signals</a>
    </nav>
  </header>
  <main id="content"></main>
</body>
</html>`);
});

app.get("/portfolio", (c) => {
  return c.html(`<!DOCTYPE html>
<html><body><h2>Portfolio</h2><p>Coming soon.</p></body></html>`);
});

app.get("/analyze", (c) => {
  return c.html(`<!DOCTYPE html>
<html><body><h2>Analysis</h2><p>Coming soon.</p></body></html>`);
});

app.get("/signals", (c) => {
  return c.html(`<!DOCTYPE html>
<html><body><h2>Signals</h2><p>Coming soon.</p></body></html>`);
});

// ── Static ─────────────────────────────────────────────────

app.get("/static/*", serveStatic({ root: "./server" }));

// ── API routes ─────────────────────────────────────────────

app.route("/api/positions", portfolioRouter);
app.route("/api/analyze", analysisRouter);
app.route("/api/signals", signalsRouter);
app.route("/api/prices", pricesRouter);

// ── Start ──────────────────────────────────────────────────

const port = parseInt(process.env.PORT ?? "3000", 10);
console.log(`DB connected: ${DatabaseFactory.path}`);
console.log(`Listening on :${port}`);
export default {
  fetch: app.fetch,
  port,
};
