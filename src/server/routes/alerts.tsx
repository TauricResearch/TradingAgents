/** @jsxImportSource hono/jsx */
/**
 * Alerts routes — CRUD for custom alert rules + matching engine view.
 */

import { Hono } from "hono"
import { DatabaseFactory } from "@lib/db"
import { cfg } from "@lib/settings"
import {
  listAlerts,
  getAlert,
  createAlert,
  deleteAlert,
  setLastTriggered,
  type AlertCondition,
} from "../lib/alerts-db.ts"
import {
  matchAlerts,
  loadPriceMap,
  tickersFromAlerts,
  type PriceData,
} from "../lib/alerts-engine.ts"
import { dispatchAlerts } from "../lib/telegram.ts"
import type { AlertRule, TriggeredAlert } from "@lib/types"
import { AlertsContent } from "../views/alerts-view.tsx"

// ── Re-exports for data layer ────────────────────────────────────────────────

export type { AlertRule, TriggeredAlert } from "@lib/types"

// ── Router ───────────────────────────────────────────────────────────────────

export const alertsRouter = new Hono()

// ── Database initialisation ──────────────────────────────────────────────────
// Connect once per process; Hono handlers call .get() which requires connect() first
DatabaseFactory.connect(cfg.portfolio.db)

// ── JSON API ─────────────────────────────────────────────────────────────────

/** GET /api/alerts — all alert rules */
alertsRouter.get("/", (c) => {
  const alerts = listAlerts()
  return c.json({ alerts })
})

/** GET /api/alerts/:id — single alert rule */
alertsRouter.get("/:id", (c) => {
  const id = parseInt(c.req.param("id"), 10)
  const alert = getAlert(id)
  if (!alert) return c.json({ error: "Alert not found" }, 404)
  return c.json({ alert })
})

/** POST /api/alerts — create a new alert rule */
alertsRouter.post("/", async (c) => {
  let body: Record<string, unknown>
  try {
    body = await c.req.json()
  } catch {
    return c.json({ error: "Invalid JSON body" }, 400)
  }

  const name = body.name as string | undefined
  const ticker = body.ticker as string | undefined
  const conditionRaw = body.condition as string | undefined
  const platform = (body.platform as string | undefined) || "all"
  const severity = (body.severity as string | undefined) || "warning"
  const message = body.message as string | undefined
  const channel = (body.channel as string | undefined) || "telegram"

  if (!name) return c.json({ error: "name is required" }, 400)
  if (!conditionRaw) return c.json({ error: "condition is required" }, 400)

  let condition: AlertCondition
  try {
    condition = JSON.parse(conditionRaw) as AlertCondition
  } catch {
    return c.json({ error: "condition must be valid JSON" }, 400)
  }

  const validSeverities = ["critical", "warning", "info"]
  if (!validSeverities.includes(severity)) {
    return c.json({ error: `severity must be one of: ${validSeverities.join(", ")}` }, 400)
  }

  const validChannels = ["telegram", "email", "webhook", "none"]
  if (!validChannels.includes(channel)) {
    return c.json({ error: `channel must be one of: ${validChannels.join(", ")}` }, 400)
  }

  try {
    const alert = createAlert({
      name,
      ticker: ticker || undefined,
      condition,
      platform,
      severity: severity as "critical" | "warning" | "info",
      message: message || undefined,
      channel: channel as "telegram" | "email" | "webhook" | "none",
    })
    return c.json({ alert }, 201)
  } catch (err) {
    if (String(err).includes("UNIQUE constraint")) {
      return c.json({ error: `An alert named "${name}" already exists.` }, 409)
    }
    return c.json({ error: String(err) }, 500)
  }
})

/** DELETE /api/alerts/:id — delete an alert rule */
alertsRouter.delete("/:id", (c) => {
  const id = parseInt(c.req.param("id"), 10)
  if (isNaN(id)) return c.json({ error: "Invalid ID" }, 400)

  const deleted = deleteAlert(id)
  if (!deleted) return c.json({ error: "Alert not found" }, 404)
  return c.json({ success: true })
})

/** GET /api/alerts/check — run matching engine, return triggered alerts */
alertsRouter.get("/check", (c) => {
  const db = DatabaseFactory.get()

  const alerts = listAlerts()
  const enabled = alerts.filter((a) => a.enabled)
  const tickers = tickersFromAlerts(enabled)
  const prices = loadPriceMap(tickers, db)
  const triggered = matchAlerts(enabled, prices)

  return c.json({
    summary: { total: alerts.length, enabled: enabled.length, triggered: triggered.length },
    triggered,
  })
})

/** POST /api/alerts/fire — run matching engine and dispatch to channels */
alertsRouter.post("/fire", async (c) => {
  const db = DatabaseFactory.get()

  const alerts = listAlerts()
  const enabled = alerts.filter((a) => a.enabled)
  const tickers = tickersFromAlerts(enabled)
  const prices = loadPriceMap(tickers, db)
  const triggered = matchAlerts(enabled, prices)

  if (triggered.length > 0) {
    const results = await dispatchAlerts(triggered)
    const ts = new Date().toISOString()
    for (let i = 0; i < triggered.length; i++) {
      const r = results[i]
      const ta = triggered[i]
      if (r !== undefined && r.sent && ta) {
        setLastTriggered(ta.alert.id, ts)
      }
    }
    return c.json({ dispatched: results, triggered })
  }

  return c.json({ dispatched: [], triggered: [] })
})

/** POST /api/alerts/check/fire — alias for /fire (backward compat) */
alertsRouter.post("/check/fire", async (c) => {
  const db = DatabaseFactory.get()

  const alerts = listAlerts()
  const enabled = alerts.filter((a) => a.enabled)
  const tickers = tickersFromAlerts(enabled)
  const prices = loadPriceMap(tickers, db)
  const triggered = matchAlerts(enabled, prices)

  if (triggered.length > 0) {
    const results = await dispatchAlerts(triggered)
    const ts = new Date().toISOString()
    for (let i = 0; i < triggered.length; i++) {
      const r = results[i]
      const ta = triggered[i]
      if (r !== undefined && r.sent && ta) {
        setLastTriggered(ta.alert.id, ts)
      }
    }
    return c.json({ dispatched: results, triggered })
  }

  return c.json({ dispatched: [], triggered: [] })
})

/** GET /api/alerts/conditions — list available condition types */
alertsRouter.get("/conditions", (c) => {
  const conditions = [
    {
      type: "price_below",
      description: "Triggers when price falls to or below threshold",
      fields: ["threshold (number)"],
      example: '{"type":"price_below","threshold":100}',
    },
    {
      type: "price_above",
      description: "Triggers when price rises to or above threshold",
      fields: ["threshold (number)"],
      example: '{"type":"price_above","threshold":200}',
    },
    {
      type: "pct_change_day",
      description: "Triggers when absolute daily % change meets or exceeds threshold",
      fields: ["threshold (number, %)"],
      example: '{"type":"pct_change_day","threshold":5}',
    },
    {
      type: "pct_change_week",
      description: "Triggers when weekly % change meets or exceeds threshold",
      fields: ["threshold (number, %)"],
      example: '{"type":"pct_change_week","threshold":10}',
    },
    {
      type: "price_cross",
      description: "Triggers when price crosses a threshold in a direction",
      fields: ["threshold (number)", "direction (up|down)"],
      example: '{"type":"price_cross","threshold":150,"direction":"down"}',
    },
  ]
  return c.json({ conditions })
})

// ── HTMX Views ───────────────────────────────────────────────────────────────

/** GET /api/alerts/view/html — full alerts view */
alertsRouter.get("/view/html", (c) => {
  const db = DatabaseFactory.get()

  const alerts = listAlerts()
  const enabled = alerts.filter((a) => a.enabled)
  const tickers = tickersFromAlerts(enabled)
  const prices = loadPriceMap(tickers, db)
  const triggered = matchAlerts(enabled, prices)

  return c.html(
    <AlertsContent
      alerts={alerts}
      triggered={triggered}
    />,
  )
})

/** GET /api/alerts/table — alerts table HTML (for HTMX refresh) */
alertsRouter.get("/table", (c) => {
  const alerts = listAlerts()
  const dot: Record<string, string> = {
    critical: "🔴",
    warning: "🟡",
    info: "🔵",
  }

  const rows = alerts.map((a) => {
    const d = dot[a.severity] ?? "⚪"
    const enabled_ = a.enabled ? "✓" : "✗"
    const lastTriggered = a.lastTriggered
      ? new Date(a.lastTriggered).toLocaleDateString("en-GB")
      : "—"
    return (
      <tr>
        <td>{a.id}</td>
        <td>{a.name}</td>
        <td>{a.ticker ?? <span class="muted">(none)</span>}</td>
        <td>{d} {a.severity}</td>
        <td>
          <code style="font-size:0.75em">{JSON.stringify(a.condition)}</code>
        </td>
        <td>{a.channel}</td>
        <td>{enabled_}</td>
        <td>{lastTriggered}</td>
        <td>
          <button
            class="btn-small btn-danger"
            hx-delete={`/api/alerts/${a.id}`}
            hx-target="closest tr"
            hx-swap="delete"
            title="Delete"
          >
            ✕
          </button>
        </td>
      </tr>
    )
  })

  return c.html(
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Name</th>
          <th>Ticker</th>
          <th>Severity</th>
          <th>Condition</th>
          <th>Channel</th>
          <th>On</th>
          <th>Last Fired</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>,
  )
})
