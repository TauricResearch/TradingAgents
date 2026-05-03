import { Hono } from "hono"
import { computeSignalAccuracy, loadPostMortems } from "../lib/feedback.ts"

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
