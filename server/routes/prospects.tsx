/** @jsxImportSource hono/jsx */

import { Hono } from "hono"
import {
  addProspect,
  deleteProspect,
  fetchProspects,
  getProspects,
  STAGES,
  updateProspectStage,
} from "../lib/prospects-data.ts"
import { ProspectsFilter, ProspectsPipeline } from "../views/prospects-view.tsx"

export const prospectsRouter = new Hono()

/** GET /api/prospects — list all watchlist items, optionally filter by platform */
prospectsRouter.get("/", (c) => {
  const stage = c.req.query("stage")
  const platform = c.req.query("platform")
  const rows = getProspects(stage || undefined, platform || undefined)
  return c.json(rows)
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
