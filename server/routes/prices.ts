import { Hono } from "hono";

export const pricesRouter = new Hono();

/**
 * GET /api/prices/:ticker — current price via yfinance subprocess
 *
 * TODO: spawn python subprocess for yfinance lookup
 * For now, returns a placeholder
 */
pricesRouter.get("/:ticker", (c) => {
  const ticker = c.req.param("ticker");
  // Placeholder — will call scripts/get_price.py
  return c.json({
    ticker,
    price: null,
    currency: "USD",
    note: "yfinance integration pending",
    timestamp: new Date().toISOString(),
  });
});
