import { Hono } from "hono";
import { loadPostMortems, computeSignalAccuracy } from "../lib/feedback.ts";

export const feedbackRouter = new Hono();

/** GET /api/feedback/post-mortems — all post-mortems */
feedbackRouter.get("/post-mortems", (c) => {
  const mortems = loadPostMortems();
  return c.json(mortems);
});

/** GET /api/feedback/accuracy — signal accuracy metrics */
feedbackRouter.get("/accuracy", (c) => {
  const mortems = loadPostMortems();
  const accuracy = computeSignalAccuracy(mortems);
  return c.json(accuracy);
});
