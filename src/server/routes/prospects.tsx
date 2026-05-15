/** @jsxImportSource hono/jsx */

import { Hono } from "hono"
import { DatabaseFactory } from "@lib/db"
import {
  addProspect,
  deleteProspect,
  fetchProspects,
  getProspects,
  STAGES,
  updateProspectStage,
} from "../lib/prospects-db.ts"
import { ResearchCoveragePanel } from "../views/prospects-view.tsx"
import { ProspectsFilter, ProspectsPipeline } from "../views/prospects-view.tsx"

// ── Types ─────────────────────────────────────────────────────────────────────

export interface CoverageGroup {
  research_doc: string
  label: string
  ticker_count: number
  high_count: number
  medium_count: number
  low_count: number
  stale_count: number
  last_update: string | null
  tickers: string[]
}

export const prospectsRouter = new Hono()

/** GET /api/prospects — list all watchlist items, optionally filter by platform */
prospectsRouter.get("/", (c) => {
  const stage = c.req.query("stage")
  const platform = c.req.query("platform")
  const rows = getProspects(stage || undefined, platform || undefined)
  return c.json(rows)
})

// ── Coverage helpers ───────────────────────────────────────────────────────────

function buildCoverageGroups(
  groups: Array<{
    research_doc: string | null
    ticker: string
    priority: string
    last_research_update: string | null
  }>,
): { groups: CoverageGroup[]; unlinked: CoverageGroup | null; total: number } {
  const STALE_DAYS = 90
  const now = new Date()
  const byDoc = new Map<string, CoverageGroup>()

  for (const row of groups) {
    const doc = row.research_doc ?? "__unlinked__"
    if (!byDoc.has(doc)) {
      byDoc.set(doc, {
        research_doc: doc === "__unlinked__" ? "" : doc,
        label: doc === "__unlinked__" ? "Unlinked" : doc.split("-").slice(1).join("-"),
        ticker_count: 0,
        high_count: 0,
        medium_count: 0,
        low_count: 0,
        stale_count: 0,
        last_update: null,
        tickers: [],
      })
    }
    const g = byDoc.get(doc)
    if (!g) continue
    g.ticker_count++
    g.tickers.push(row.ticker)
    if (row.priority === "high") g.high_count++
    else if (row.priority === "medium") g.medium_count++
    else g.low_count++
    if (row.last_research_update) {
      if (!g.last_update || row.last_research_update > g.last_update) {
        g.last_update = row.last_research_update
      }
      const updated = new Date(row.last_research_update)
      const threshold = new Date(now)
      threshold.setDate(threshold.getDate() - STALE_DAYS)
      if (updated < threshold) g.stale_count++
    } else if (!row.research_doc) {
      g.stale_count++
    }
  }

  const linked = [...byDoc.values()].filter((g) => g.research_doc !== "")
  const unlinked = byDoc.get("__unlinked__") ?? null
  return { groups: linked, unlinked, total: groups.length }
}

function fetchCoverageRows(db: ReturnType<typeof DatabaseFactory.get>) {
  return db
    .query<
      { research_doc: string | null; ticker: string; priority: string; last_research_update: string | null },
      []
    >(
      `SELECT research_doc, ticker, priority, last_research_update
       FROM watchlist
       ORDER BY CASE WHEN research_doc IS NULL THEN 1 ELSE 0 END, research_doc, priority DESC, ticker`,
    )
    .all()
}

/** GET /api/prospects/coverage — research coverage summary by doc */
prospectsRouter.get("/coverage", (c) => {
  const db = DatabaseFactory.get()
  const groups = fetchCoverageRows(db)
  return c.json(buildCoverageGroups(groups))
})

/** GET /api/prospects/coverage/html — research coverage panel as HTML */
prospectsRouter.get("/coverage/html", async (c) => {
  const db = DatabaseFactory.get()
  const rows = fetchCoverageRows(db)
  const { groups, unlinked, total } = buildCoverageGroups(rows)
  return c.html(<ResearchCoveragePanel groups={groups} unlinked={unlinked} total={total} />)
})

/** GET /api/prospects/html — prospects pipeline as HTML for HTMX */
prospectsRouter.get("/html", async (c) => {
  try {
    const platform = c.req.query("platform") || ""
    const items = await fetchProspects(platform || undefined)
    return c.html(
      <>
        <ProspectsFilter selectedPlatform={platform} />
        <ProspectsPipeline items={items} selectedPlatform={platform} />
      </>,
    )
  } catch (e: unknown) {
    return c.html(
      <div class="error-card">
        <strong>Prospects error</strong>
        <br />
        {(e as Error).message}
      </div>,
      500,
    )
  }
})

/** POST /api/prospects — add ticker to watchlist */
prospectsRouter.post("/", async (c) => {
  const body = await c.req.json()
  const { ticker, exchange, platform, thesis, priority } = body

  if (!ticker) {
    return c.html(<div id="prospect-error" class="error-card">ticker is required</div>, 400)
  }

  try {
    addProspect({ ticker, exchange, platform, thesis, priority })
    const items = await fetchProspects()
    return c.html(
      <>
        <ProspectsFilter selectedPlatform="" />
        <ProspectsPipeline items={items} selectedPlatform="" />
      </>,
    )
  } catch (e: unknown) {
    if ((e as Error).message.includes("UNIQUE")) {
      return c.html(
        <div id="prospect-error" class="error-card">{ticker} already on watchlist</div>,
        409,
      )
    }
    throw e
  }
})

/** POST /api/prospects/:id/stage — advance stage */
prospectsRouter.post("/:id/stage", async (c) => {
  const id = c.req.param("id")
  const body = await c.req.json()
  const { stage } = body

  if (!STAGES.includes(stage as (typeof STAGES)[number])) {
    return c.html(
      <div class="error-card">Invalid stage. Must be: {STAGES.join(", ")}</div>,
      400,
    )
  }

  const result = updateProspectStage(id, stage)
  if (result === 0) {
    return c.html(<div class="error-card">Prospect not found</div>, 404)
  }

  const items = await fetchProspects()
  return c.html(
    <>
      <ProspectsFilter selectedPlatform="" />
      <ProspectsPipeline items={items} selectedPlatform="" />
    </>,
  )
})

/** DELETE /api/prospects/:id — remove from watchlist */
prospectsRouter.delete("/:id", async (c) => {
  const id = c.req.param("id")
  const result = deleteProspect(id)
  if (result === 0) {
    return c.html(<div class="error-card">Prospect not found</div>, 404)
  }

  const items = await fetchProspects()
  return c.html(
    <>
      <ProspectsFilter selectedPlatform="" />
      <ProspectsPipeline items={items} selectedPlatform="" />
    </>,
  )
})