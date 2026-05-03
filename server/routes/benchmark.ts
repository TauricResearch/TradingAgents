import { Hono } from "hono"
import { getBenchmark } from "../lib/benchmark.ts"

export const benchmarkRouter = new Hono()

/** GET /api/benchmark — portfolio vs. benchmark returns */
benchmarkRouter.get("/", async (c) => {
  try {
    const result = await getBenchmark()
    return c.json(result)
  } catch (e: unknown) {
    return c.json(
      {
        error: "Benchmark check failed",
        detail: (e as Error).message,
        hint: "Ensure yfinance is installed (uv pip install yfinance)",
      },
      500,
    )
  }
})
