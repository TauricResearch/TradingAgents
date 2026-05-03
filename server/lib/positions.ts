/**
 * Position exit plans — YAML files per ticker, organized by platform.
 *
 * Location: ~/.tradingagents/positions/{platform}/{TICKER}.yaml
 *   e.g. ~/.tradingagents/positions/degiero/AAPL.yaml
 *   e.g. ~/.tradingagents/positions/ibkr/MSFT.yaml
 *
 * Each file defines entry thesis, invalidation conditions,
 * profit targets, and time stops. The frontmatter YAML must include
 * a `platform:` field; legacy files without it default to "unknown".
 */

import { existsSync, lstatSync, readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { load } from "js-yaml"

const POSITIONS_DIR =
  process.env.POSITIONS_DIR ?? join(process.env.HOME ?? "/tmp", ".tradingagents", "positions")

function entryIsDirectory(path: string): boolean {
  try {
    return lstatSync(path).isDirectory()
  } catch {
    return false
  }
}

export interface ExitTarget {
  price: number
  label: string
  fraction: number
}

export interface ExitPlan {
  ticker: string
  platform: string // e.g. "degiero", "ibkr", "pension:nn", "test", "unknown"
  entry_date: string
  entry_price: number
  quantity: number
  thesis: string
  invalidation: {
    price: number
    thesis: string
  }
  // Backward-compat: some YAML files use flat fields (invalidation_price / invalidation_thesis)
  invalidation_price?: number
  invalidation_thesis?: string
  targets: ExitTarget[]
  time_stop?: string
  notes?: string
}

export interface ExitStatus {
  plan: ExitPlan
  currentPrice?: number
  pnl: number
  pnlPct: number
  distanceToStop: number
  distanceToStopPct: number
  nextTarget?: ExitTarget
  distanceToTarget?: number
  distanceToTargetPct?: number
  targetsHit: number
  timeStopDaysLeft?: number
}

/**
 * Load all exit plans from the positions directory.
 */
export function loadAllPlans(): ExitPlan[] {
  const base = POSITIONS_DIR
  if (!existsSync(base)) return []

  const plans: ExitPlan[] = []

  for (const entry of readdirSync(base)) {
    const entryPath = join(base, entry)

    // Handle platform sub-directories (e.g. positions/degiero/AAPL.yaml)
    if (entryIsDirectory(entryPath)) {
      const platform = entry // directory name = platform
      for (const file of readdirSync(entryPath)) {
        if (!file.endsWith(".yaml") && !file.endsWith(".yml")) continue
        try {
          const raw = readFileSync(join(entryPath, file), "utf-8")
          const plan = load(raw) as ExitPlan
          if (plan.ticker) {
            plans.push({ ...plan, platform: plan.platform || platform })
          }
        } catch {
          // Skip malformed files
        }
      }
      continue
    }

    // Handle flat directory (legacy: positions/TICKER.yaml → platform "unknown")
    if (entry.endsWith(".yaml") || entry.endsWith(".yml")) {
      try {
        const raw = readFileSync(join(base, entry), "utf-8")
        const plan = load(raw) as ExitPlan
        if (plan.ticker) {
          plans.push({ ...plan, platform: plan.platform || "unknown" })
        }
      } catch {
        // Skip malformed files
      }
    }
  }

  return plans
}

/**
 * Load a single exit plan by ticker.
 */
export function loadPlan(ticker: string, platform?: string): ExitPlan | null {
  // Try platform-aware path first
  if (platform && platform !== "unknown") {
    const path = join(POSITIONS_DIR, platform, `${ticker}.yaml`)
    if (existsSync(path)) {
      try {
        const raw = readFileSync(path, "utf-8")
        const plan = load(raw) as ExitPlan
        return { ...plan, platform: plan.platform || platform }
      } catch {
        // Fall through to flat lookup
      }
    }
  }

  // Flat lookup (legacy or fallback)
  const flatPath = join(POSITIONS_DIR, `${ticker}.yaml`)
  if (existsSync(flatPath)) {
    try {
      const raw = readFileSync(flatPath, "utf-8")
      const plan = load(raw) as ExitPlan
      return { ...plan, platform: plan.platform || "unknown" }
    } catch {
      return null
    }
  }

  return null
}

/**
 * Compute exit status for a plan given a current price.
 */
export function computeExitStatus(plan: ExitPlan, currentPrice?: number): ExitStatus {
  // Backward-compat: normalize flat YAML fields (invalidation_price/thesis)
  // to nested object format (invalidation: { price, thesis })
  const invalidation = plan.invalidation ?? {
    price: plan.invalidation_price ?? 0,
    thesis: plan.invalidation_thesis ?? "",
  }

  const pnl = currentPrice ? (currentPrice - plan.entry_price) * plan.quantity : 0
  const pnlPct = currentPrice ? ((currentPrice - plan.entry_price) / plan.entry_price) * 100 : 0
  const distanceToStop = currentPrice ? currentPrice - invalidation.price : 0
  const distanceToStopPct = currentPrice
    ? ((currentPrice - invalidation.price) / currentPrice) * 100
    : 0

  // Find next target not yet hit
  const targets = plan.targets ?? []
  const targetsHit = currentPrice ? targets.filter((t) => currentPrice >= t.price).length : 0
  const nextTarget = targets.find((t) => !currentPrice || currentPrice < t.price)
  const distanceToTarget = nextTarget && currentPrice ? nextTarget.price - currentPrice : undefined
  const distanceToTargetPct =
    nextTarget && currentPrice
      ? ((nextTarget.price - currentPrice) / currentPrice) * 100
      : undefined

  // Time stop days remaining
  let timeStopDaysLeft: number | undefined
  if (plan.time_stop) {
    const stopDate = new Date(plan.time_stop)
    const now = new Date()
    const diff = stopDate.getTime() - now.getTime()
    timeStopDaysLeft = Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)))
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
  }
}
