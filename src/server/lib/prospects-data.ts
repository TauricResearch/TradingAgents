/** Prospects data layer — extracted from route for reuse. */
import { DatabaseFactory } from "../../lib/db.ts"
import { sanitizeForDb } from "./sanitize.ts"

export interface Prospect {
  id: number
  ticker: string
  platform: string
  stage: string
  priority: string
  thesis: string | null
  last_signal: string | null
}

export const STAGES = ["researching", "analyzed", "candidate", "approved", "acquired"] as const

export async function fetchProspects(platform?: string): Promise<Prospect[]> {
  const db = DatabaseFactory.get()
  let rows: unknown[]
  if (platform) {
    rows = db
      .query(
        "SELECT * FROM watchlist WHERE platform = ? AND stage != 'acquired' ORDER BY priority DESC, added_date DESC",
      )
      .all(platform)
  } else {
    rows = db
      .query(
        "SELECT * FROM watchlist WHERE stage != 'acquired' ORDER BY priority DESC, added_date DESC",
      )
      .all()
  }
  return rows as Prospect[]
}

export function getProspects(stage?: string, platform?: string): Prospect[] {
  const db = DatabaseFactory.get()
  if (stage && platform) {
    return db
      .query(
        "SELECT * FROM watchlist WHERE stage = ? AND platform = ? ORDER BY priority DESC, added_date DESC",
      )
      .all(stage, platform) as Prospect[]
  }
  if (platform) {
    return db
      .query(
        "SELECT * FROM watchlist WHERE platform = ? AND stage != 'acquired' ORDER BY priority DESC, added_date DESC",
      )
      .all(platform) as Prospect[]
  }
  if (stage) {
    return db
      .query("SELECT * FROM watchlist WHERE stage = ? ORDER BY priority DESC, added_date DESC")
      .all(stage) as Prospect[]
  }
  return db
    .query(
      "SELECT * FROM watchlist WHERE stage != 'acquired' ORDER BY priority DESC, added_date DESC",
    )
    .all() as Prospect[]
}

export function addProspect(body: {
  ticker: string
  exchange?: string
  platform?: string
  thesis?: string
  priority?: string
}): void {
  const db = DatabaseFactory.get()
  const { ticker, exchange, platform, thesis, priority } = body
  const stmt = db.prepare(
    "INSERT INTO watchlist (ticker, exchange, platform, thesis, priority, added_date) VALUES (?, ?, ?, ?, ?, ?)",
  )
  stmt.run(
    ticker,
    exchange ?? "US",
    platform ?? "unknown",
    sanitizeForDb(thesis) ?? null,
    priority ?? "medium",
    new Date().toISOString().slice(0, 10),
  )
}

export function updateProspectStage(id: string, stage: string): number {
  const db = DatabaseFactory.get()
  const result = db.prepare("UPDATE watchlist SET stage = ? WHERE id = ?").run(stage, id)
  return result.changes
}

export function deleteProspect(id: string): number {
  const db = DatabaseFactory.get()
  const result = db.prepare("DELETE FROM watchlist WHERE id = ?").run(id)
  return result.changes
}
