/**
 * GET /api/positions/exits — exit status for all planned positions
 */
import { Hono } from "hono";
import { loadAllPlans, computeExitStatus } from "../lib/positions.ts";

export const exitsRouter = new Hono();

exitsRouter.get("/", async (c) => {
  const plans = loadAllPlans();
  const statuses = plans.map((plan) => {
    // In production, fetch live price here; for now pass undefined
    return computeExitStatus(plan, undefined);
  });
  return c.json(statuses);
});
