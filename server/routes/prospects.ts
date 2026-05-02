import { Hono } from "hono";
import { DatabaseFactory } from "../lib/db.ts";

export const prospectsRouter = new Hono();

const STAGES = ["researching", "analyzed", "candidate", "approved", "acquired"] as const;

/** GET /api/prospects — list all watchlist items with stage */
prospectsRouter.get("/", (c) => {
  const db = DatabaseFactory.get();
  const stage = c.req.query("stage");

  let query = "SELECT * FROM watchlist WHERE stage != 'acquired' ORDER BY priority DESC, added_date DESC";
  const params: (string | number | null)[] = [];

  if (stage) {
    query = "SELECT * FROM watchlist WHERE stage = ? ORDER BY priority DESC, added_date DESC";
    params.push(stage);
  }

  const rows = db.query(query).all(...params);
  return c.json(rows);
});

/** POST /api/prospects — add ticker to watchlist */
prospectsRouter.post("/", async (c) => {
  const db = DatabaseFactory.get();
  const body = await c.req.json();
  const { ticker, exchange, thesis, priority } = body;

  if (!ticker) {
    return c.json({ error: "ticker is required" }, 400);
  }

  try {
    const stmt = db.prepare(
      "INSERT INTO watchlist (ticker, exchange, thesis, priority, added_date) VALUES (?, ?, ?, ?, ?)",
    );
    const result = stmt.run(
      ticker,
      exchange ?? "US",
      thesis ?? null,
      priority ?? "medium",
      new Date().toISOString().slice(0, 10),
    );
    return c.json({ id: result.lastInsertRowid, ticker, stage: "researching" }, 201);
  } catch (e: unknown) {
    if ((e as Error).message.includes("UNIQUE")) {
      return c.json({ error: `${ticker} already on watchlist` }, 409);
    }
    throw e;
  }
});

/** POST /api/prospects/:id/stage — advance stage */
prospectsRouter.post("/:id/stage", async (c) => {
  const db = DatabaseFactory.get();
  const id = c.req.param("id");
  const body = await c.req.json();
  const { stage } = body;

  if (!STAGES.includes(stage as (typeof STAGES)[number])) {
    return c.json({ error: `Invalid stage. Must be: ${STAGES.join(", ")}` }, 400);
  }

  const result = db.prepare("UPDATE watchlist SET stage = ? WHERE id = ?").run(stage, id);
  if (result.changes === 0) {
    return c.json({ error: "Prospect not found" }, 404);
  }

  return c.json({ id, stage });
});

/** DELETE /api/prospects/:id — remove from watchlist */
prospectsRouter.delete("/:id", (c) => {
  const db = DatabaseFactory.get();
  const id = c.req.param("id");
  const result = db.prepare("DELETE FROM watchlist WHERE id = ?").run(id);
  if (result.changes === 0) {
    return c.json({ error: "Prospect not found" }, 404);
  }
  return c.json({ id, deleted: true });
});
