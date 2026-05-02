import { Hono } from "hono";
import { DEFAULT_RULES, checkRules, suggestRebalance } from "../lib/governance.ts";
import { getHoldings } from "../lib/hledger.ts";

export const governanceRouter = new Hono();

/** GET /api/governance/rules — list all governance rules */
governanceRouter.get("/rules", (c) => c.json(DEFAULT_RULES));

/** GET /api/governance/check — evaluate current holdings against rules */
governanceRouter.get("/check", async (c) => {
  try {
    const { holdings, cash } = await getHoldings();
    if (holdings.length === 0) {
      return c.json({ violations: [], suggestions: [], note: "No holdings loaded" });
    }

    const totalCost = holdings.reduce((s, h) => s + h.costBasis, 0);
    const cashTotal = cash.reduce((s, c) => s + c.amount, 0);
    const portfolioValue = totalCost + cashTotal;

    const allocations = holdings.map((h) => ({
      ticker: h.ticker,
      value: h.costBasis,
      weight: portfolioValue > 0 ? (h.costBasis / portfolioValue) * 100 : 0,
    }));

    const cashPct = portfolioValue > 0 ? (cashTotal / portfolioValue) * 100 : 0;

    // Peak value — in production, track this; for now use current
    const peakValue = portfolioValue;

    const violations = checkRules(allocations, cashPct, peakValue, portfolioValue);
    const suggestions = suggestRebalance(allocations, cashPct);

    return c.json({
      portfolioValue,
      cashPct,
      violations,
      suggestions,
    });
  } catch (e: unknown) {
    return c.json({ error: "Governance check failed", detail: (e as Error).message }, 500);
  }
});
