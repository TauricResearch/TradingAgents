import { Hono } from "hono"
import { getHoldings, getPrices, getAllocation } from "../lib/hledger.ts"

export const holdingsRouter = new Hono()

/** GET /api/holdings — current holdings from hLedger */
holdingsRouter.get("/", async (c) => {
  try {
    const result = await getHoldings()
    return c.json(result)
  } catch (e: unknown) {
    return c.json(
      {
        error: "hLedger error",
        detail: (e as Error).message,
        hint: "Check HLEDGER_FILE env var and journal file syntax",
      },
      500,
    )
  }
})

/** GET /api/holdings/prices — price history from hLedger */
holdingsRouter.get("/prices", async (c) => {
  try {
    const prices = await getPrices()
    return c.json(prices)
  } catch (e: unknown) {
    return c.json(
      {
        error: "hLedger error",
        detail: (e as Error).message,
      },
      500,
    )
  }
})

/** GET /api/holdings/allocation — allocation tree (human-readable) */
holdingsRouter.get("/allocation", async (c) => {
  try {
    const text = await getAllocation()
    return c.text(text)
  } catch (e: unknown) {
    return c.json(
      {
        error: "hLedger error",
        detail: (e as Error).message,
      },
      500,
    )
  }
})
