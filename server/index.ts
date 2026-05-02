import { Hono } from "hono";
import { serveStatic } from "hono/bun";
import { readFileSync, existsSync } from "node:fs";
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

// ── View helpers ───────────────────────────────────────────

const viewsDir = join(import.meta.dir, "views");

function view(name: string): string {
  const path = join(viewsDir, name);
  return existsSync(path) ? readFileSync(path, "utf-8") : `<p>View not found: ${name}</p>`;
}

function renderPage(content: string): string {
  const layout = view("layout.html");
  return layout.replace("{{{content}}}", content);
}

// ── Pages ──────────────────────────────────────────────────

app.get("/", (c) => {
  return c.html(renderPage(view("partials/portfolio.html")));
});

app.get("/portfolio", (c) => {
  return c.html(renderPage(view("partials/portfolio.html")));
});

app.get("/analyze", (c) => {
  return c.html(renderPage(view("partials/analysis.html")));
});

app.get("/signals", (c) => {
  return c.html(renderPage(view("partials/signals.html")));
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
  idleTimeout: 240, // 4 minutes for long-running analyses
};
