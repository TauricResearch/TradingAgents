/**
 * Alert rules CRUD via SQLite.
 * All access MUST go through DatabaseFactory.
 *
 * Bun SQLite patterns (confirmed against signals-data.ts, prospects-data.ts):
 *   - Selects: db.query("...").all() or db.query("...", [args]).all()
 *   - Mutates: db.prepare("...").run(...args)
 *   - Type args only on query(), not on prepare()
 */

import { DatabaseFactory } from "../../lib/db.ts"
import type { AlertRule } from "./types.ts"

// ── Types ───────────────────────────────────────────────────────────────────

export interface AlertCondition {
  type:
    | "price_below"
    | "price_above"
    | "pct_change_day"
    | "pct_change_week"
    | "signal_change"
    | "price_cross"
  threshold?: number
  direction?: "up" | "down"
}

interface DbAlert {
  id: number
  name: string
  ticker: string | null
  condition: string
  platform: string
  severity: "critical" | "warning" | "info"
  message: string | null
  channel: "telegram" | "email" | "webhook" | "none"
  enabled: number
  last_checked: string | null
  last_triggered: string | null
  created_at: string
  updated_at: string
}

function rowToRule(row: DbAlert): AlertRule {
  let condition: AlertCondition
  try {
    condition = JSON.parse(row.condition) as AlertCondition
  } catch {
    throw new Error(`Alert ${row.id} has malformed condition JSON: ${row.condition}`)
  }

  return {
    id: row.id,
    name: row.name,
    ticker: row.ticker,
    condition,
    platform: row.platform,
    severity: row.severity,
    message: row.message,
    channel: row.channel,
    enabled: Boolean(row.enabled),
    lastChecked: row.last_checked,
    lastTriggered: row.last_triggered,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  }
}

// ── CRUD ─────────────────────────────────────────────────────────────────────

export function listAlerts(): AlertRule[] {
  const db = DatabaseFactory.get()
  const rows = db.query("SELECT * FROM alerts ORDER BY created_at DESC").all() as DbAlert[]
  return rows.map(rowToRule)
}

export function getAlert(id: number): AlertRule | null {
  const db = DatabaseFactory.get()
  const stmt = db.query("SELECT * FROM alerts WHERE id = ?")
  const row = stmt.get(id) as DbAlert | null
  return row ? rowToRule(row) : null
}

export interface CreateAlertParams {
  name: string
  ticker?: string
  condition: AlertCondition
  platform?: string
  severity?: "critical" | "warning" | "info"
  message?: string
  channel?: "telegram" | "email" | "webhook" | "none"
  enabled?: boolean
}

export function createAlert(params: CreateAlertParams): AlertRule {
  const db = DatabaseFactory.get()
  const {
    name,
    ticker = null,
    condition,
    platform = "all",
    severity = "warning",
    message = null,
    channel = "telegram",
    enabled = true,
  } = params

  const conditionJson = JSON.stringify(condition)

  const stmt = db.prepare(
    `INSERT INTO alerts (name, ticker, condition, platform, severity, message, channel, enabled)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
  )
  const result = stmt.run(
    name,
    ticker,
    conditionJson,
    platform,
    severity,
    message,
    channel,
    enabled ? 1 : 0,
  )

  const created = getAlert(Number(result.lastInsertRowid))
  if (!created) throw new Error(`Failed to retrieve created alert`)
  return created
}

export function updateAlert(
  id: number,
  patch: Partial<Omit<CreateAlertParams, "condition"> & { condition?: AlertCondition }>,
): AlertRule | null {
  const db = DatabaseFactory.get()
  const existing = getAlert(id)
  if (!existing) return null

  const fields: string[] = []
  const values: (string | number | null)[] = []

  if (patch.name !== undefined) {
    fields.push("name = ?")
    values.push(patch.name)
  }
  if (patch.ticker !== undefined) {
    fields.push("ticker = ?")
    values.push(patch.ticker ?? null)
  }
  if (patch.condition !== undefined) {
    fields.push("condition = ?")
    values.push(JSON.stringify(patch.condition))
  }
  if (patch.platform !== undefined) {
    fields.push("platform = ?")
    values.push(patch.platform)
  }
  if (patch.severity !== undefined) {
    fields.push("severity = ?")
    values.push(patch.severity)
  }
  if (patch.message !== undefined) {
    fields.push("message = ?")
    values.push(patch.message ?? null)
  }
  if (patch.channel !== undefined) {
    fields.push("channel = ?")
    values.push(patch.channel)
  }
  if (patch.enabled !== undefined) {
    fields.push("enabled = ?")
    values.push(patch.enabled ? 1 : 0)
  }

  fields.push("updated_at = datetime('now')")
  values.push(id)

  if (fields.length === 1) return existing

  db.prepare(`UPDATE alerts SET ${fields.join(", ")} WHERE id = ?`).run(...values)

  return getAlert(id)
}

export function deleteAlert(id: number): boolean {
  const db = DatabaseFactory.get()
  const result = db.prepare("DELETE FROM alerts WHERE id = ?").run(id)
  return result.changes > 0
}

export function setLastChecked(id: number, timestamp: string): void {
  const db = DatabaseFactory.get()
  db.prepare("UPDATE alerts SET last_checked = ? WHERE id = ?").run(timestamp, id)
}

export function setLastTriggered(id: number, timestamp: string): void {
  const db = DatabaseFactory.get()
  db.prepare("UPDATE alerts SET last_triggered = ?, last_checked = ? WHERE id = ?").run(
    timestamp,
    timestamp,
    id,
  )
}
