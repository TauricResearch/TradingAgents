/**
 * POST /api/portfolio/balance — update manual account balance
 *
 * Body: { account_id, balance, note? }
 */
import { Hono } from "hono"
import { DatabaseFactory } from "../../lib/db.ts"

export const portfolioBalanceRouter = new Hono()

portfolioBalanceRouter.post("/", async (c) => {
  try {
    const body = await c.req.json()
    const { account_id, balance, note } = body

    if (!account_id) return c.json({ error: "account_id is required" }, 400)
    if (typeof balance !== "number" || Number.isNaN(balance)) {
      return c.json({ error: "balance must be a number" }, 400)
    }

    const db = DatabaseFactory.get()
    const date = new Date().toISOString().split("T")[0]

    // Update existing account balance (preserve non-NULL columns)
    const existing = db.query("SELECT * FROM accounts WHERE id = ?").get(account_id)
    if (!existing) return c.json({ error: "Account not found", account_id }, 404)

    db.run("UPDATE accounts SET balance = ?, updated_at = datetime('now') WHERE id = ?", [
      balance,
      account_id,
    ])

    // Record balance history
    db.run("INSERT INTO account_balances (account_id, balance, date, note) VALUES (?, ?, ?, ?)", [
      account_id,
      balance,
      date,
      note ?? null,
    ])

    return c.json({ ok: true, account_id, balance, date })
  } catch (e: unknown) {
    const msg = (e as Error).message
    if (msg.includes("UNIQUE constraint failed")) {
      return c.json({ error: "Account not found", detail: msg }, 404)
    }
    return c.json({ error: "Failed to update balance", detail: msg }, 500)
  }
})
