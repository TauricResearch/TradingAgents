/** @jsxImportSource hono/jsx */


/**
 * GET /api/positions/exits — exit status for all planned positions
 *
 * Fetches live prices for each ticker, then computes exit status
 * (P&L, distance to stop, distance to targets).
 *
 * Price cache: daily (expires at midnight UTC) — one fetch per ticker per calendar day.
 * Response cache: 30s — shared with /api/positions/exits/html via buildExitStatuses().
 */
import { Hono } from "hono"
import { buildExitStatuses } from "../lib/exits-data.ts"
import { ExitList } from "../views/exit-list.tsx"

export const exitsRouter = new Hono()

/** GET /api/positions/exits — JSON exit statuses */
exitsRouter.get("/", async (c) => {
  const statuses = await buildExitStatuses()
  return c.json(statuses)
})

/** GET /api/positions/exits/html — exit plans as HTML for HTMX */
exitsRouter.get("/html", async (c) => {
  try {
    const statuses = await buildExitStatuses()
    return c.html(<ExitList statuses={statuses} />)
  } catch (e: unknown) {
    return c.html(
      <div class="error-card">
        <strong>Exits error</strong>
        <br />
        {(e as Error).message}
      </div>,
      500,
    )
  }
})
