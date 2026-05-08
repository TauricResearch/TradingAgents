/** @jsxImportSource hono/jsx */


/**
 * GET /api/workflow — unified position lifecycle data for Kanban pipeline.
 *
 * Returns three stages:
 *   approved     — open DB positions with no exit plan yet
 *   holdings     — open positions with exit plan, no urgency signal
 *   pendingExit  — open positions with exit plan AND urgency signal
 *
 * hledger is the authoritative source for real holdings.
 * Only positions for platforms with actual hledger holdings are shown.
 * Empty hledger → empty workflow (clean, no phantom positions).
 *
 * Price cache: daily (expires at midnight UTC) — shared with exits.ts via ../lib/cache.ts.
 */
import { Hono } from "hono"
import { DatabaseFactory } from "../../lib/db.ts"
import { buildWorkflowData } from "../lib/workflow-data.ts"
import { WorkflowKanban } from "../views/workflow-kanban.tsx"

export const workflowRouter = new Hono()

/** GET /api/workflow — JSON data for the kanban pipeline */
workflowRouter.get("/", async (c) => {
  const data = await buildWorkflowData()
  return c.json(data)
})

/** GET /api/workflow/html — workflow kanban as HTML for HTMX */
workflowRouter.get("/html", async (c) => {
  try {
    const data = await buildWorkflowData()
    return c.html(<WorkflowKanban data={data} />)
  } catch (e: unknown) {
    return c.html(
      <div class="error-card">
        <strong>Workflow error</strong>
        <br />
        {(e as Error).message}
      </div>,
      500,
    )
  }
})

/** POST /api/workflow/close/:id — close a position and return workflow HTML */
workflowRouter.post("/close/:id", async (c) => {
  const db = DatabaseFactory.get()
  const id = c.req.param("id")
  const result = db.prepare("UPDATE positions SET status = 'closed' WHERE id = ?").run(id)
  if (result.changes === 0) {
    return c.html(
      <div class="error-card">
        <strong>Position not found</strong>
      </div>,
      404,
    )
  }

  // Re-fetch workflow data and return HTML
  const data = await buildWorkflowData()
  return c.html(<WorkflowKanban data={data} />)
})
