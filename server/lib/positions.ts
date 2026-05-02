/**
 * Position exit plans — YAML files per ticker.
 *
 * Location: ~/.tradingagents/positions/{TICKER}.yaml
 * Each file defines entry thesis, invalidation conditions,
 * profit targets, and time stops.
 */

import { readdirSync, existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { load } from "js-yaml";

const POSITIONS_DIR =
  process.env.POSITIONS_DIR ?? join(process.env.HOME ?? "/tmp", ".tradingagents", "positions");

export interface ExitTarget {
  price: number;
  label: string;
  fraction: number;
}

export interface ExitPlan {
  ticker: string;
  entry_date: string;
  entry_price: number;
  quantity: number;
  thesis: string;
  invalidation: {
    price: number;
    thesis: string;
  };
  targets: ExitTarget[];
  time_stop?: string;
  notes?: string;
}

export interface ExitStatus {
  plan: ExitPlan;
  currentPrice?: number;
  pnl: number;
  pnlPct: number;
  distanceToStop: number;
  distanceToStopPct: number;
  nextTarget?: ExitTarget;
  distanceToTarget?: number;
  distanceToTargetPct?: number;
  targetsHit: number;
  timeStopDaysLeft?: number;
}

/**
 * Load all exit plans from the positions directory.
 */
export function loadAllPlans(): ExitPlan[] {
  if (!existsSync(POSITIONS_DIR)) return [];

  const plans: ExitPlan[] = [];
  for (const file of readdirSync(POSITIONS_DIR)) {
    if (!file.endsWith(".yaml") && !file.endsWith(".yml")) continue;
    try {
      const raw = readFileSync(join(POSITIONS_DIR, file), "utf-8");
      const plan = load(raw) as ExitPlan;
      if (plan.ticker) plans.push(plan);
    } catch {
      // Skip malformed files
    }
  }
  return plans;
}

/**
 * Load a single exit plan by ticker.
 */
export function loadPlan(ticker: string): ExitPlan | null {
  const path = join(POSITIONS_DIR, `${ticker}.yaml`);
  if (!existsSync(path)) return null;
  try {
    const raw = readFileSync(path, "utf-8");
    return load(raw) as ExitPlan;
  } catch {
    return null;
  }
}

/**
 * Compute exit status for a plan given a current price.
 */
export function computeExitStatus(plan: ExitPlan, currentPrice?: number): ExitStatus {
  const pnl = currentPrice ? (currentPrice - plan.entry_price) * plan.quantity : 0;
  const pnlPct = currentPrice ? ((currentPrice - plan.entry_price) / plan.entry_price) * 100 : 0;
  const distanceToStop = currentPrice ? currentPrice - plan.invalidation.price : 0;
  const distanceToStopPct = currentPrice
    ? ((currentPrice - plan.invalidation.price) / currentPrice) * 100
    : 0;

  // Find next target not yet hit
  const targets = plan.targets ?? [];
  const targetsHit = currentPrice
    ? targets.filter((t) => currentPrice >= t.price).length
    : 0;
  const nextTarget = targets.find((t) => !currentPrice || currentPrice < t.price);
  const distanceToTarget =
    nextTarget && currentPrice ? nextTarget.price - currentPrice : undefined;
  const distanceToTargetPct =
    nextTarget && currentPrice ? ((nextTarget.price - currentPrice) / currentPrice) * 100 : undefined;

  // Time stop days remaining
  let timeStopDaysLeft: number | undefined;
  if (plan.time_stop) {
    const stopDate = new Date(plan.time_stop);
    const now = new Date();
    const diff = stopDate.getTime() - now.getTime();
    timeStopDaysLeft = Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
  }

  return {
    plan,
    currentPrice,
    pnl,
    pnlPct,
    distanceToStop,
    distanceToStopPct,
    nextTarget,
    distanceToTarget,
    distanceToTargetPct,
    targetsHit,
    timeStopDaysLeft,
  };
}
