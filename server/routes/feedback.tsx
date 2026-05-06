/** @jsxImportSource hono/jsx */

import { Hono } from "hono"
import {
  computeCorrelations,
  computeSignalAccuracy,
  loadPostMortems,
} from "../lib/feedback-data.ts"
import {
  AccuracyPanel,
  CorrelationsTable,
  PostMortemsList,
} from "../views/feedback-view.tsx"

export const feedbackRouter = new Hono()

/** GET /api/feedback — aggregated accuracy + post-mortems */
feedbackRouter.get("/", (c) => {
  const mortems = loadPostMortems()
  const accuracy = computeSignalAccuracy(mortems)
  return c.json({ accuracy, postMortems: mortems })
})

/** GET /api/feedback/post-mortems — all post-mortems */
feedbackRouter.get("/post-mortems", (c) => {
  const mortems = loadPostMortems()
  return c.json(mortems)
})

/** GET /api/feedback/accuracy — signal accuracy metrics */
feedbackRouter.get("/accuracy", (c) => {
  const mortems = loadPostMortems()
  const accuracy = computeSignalAccuracy(mortems)
  return c.json(accuracy)
})

/** GET /api/feedback/with-positions — signals correlated with position outcomes */
feedbackRouter.get("/with-positions", async (c) => {
  const data = await computeCorrelations()
  return c.json(data)
})

/** GET /api/feedback/accuracy/html — accuracy as HTML for HTMX */
feedbackRouter.get("/accuracy/html", (c) => {
  const mortems = loadPostMortems()
  const accuracy = computeSignalAccuracy(mortems)
  return c.html(<AccuracyPanel accuracy={accuracy} />)
})

/** GET /api/feedback/post-mortems/html — post-mortems as HTML for HTMX */
feedbackRouter.get("/post-mortems/html", (c) => {
  const mortems = loadPostMortems()
  return c.html(<PostMortemsList mortems={mortems} />)
})

/** GET /api/feedback/with-positions/html — correlations as HTML for HTMX */
feedbackRouter.get("/with-positions/html", async (c) => {
  try {
    const data = await computeCorrelations()
    return c.html(<CorrelationsTable data={data} />)
  } catch (e: unknown) {
    return c.html(
      <div class="error-card">
        <strong>Feedback error</strong>
        <br />
        {(e as Error).message}
      </div>,
      500,
    )
  }
})
