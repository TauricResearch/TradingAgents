/**
 * Shared CLI argument definitions for citty commands.
 * Import and reuse across subcommands for consistency.
 *
 * Defaults are pulled from src/server/lib/settings.ts so they are
 * configurable in one place (settings.json).
 */

import { cfg } from "../../server/lib/settings.ts"

export const tickerArg = {
  type: "positional" as const,
  description: "Stock ticker symbol (e.g., AAPL, TKA.DE)",
  required: true,
}

export const platformArg = {
  type: "string" as const,
  description: "Platform (ajbell, aviva, ig, nsandi)",
  alias: "p",
  default: cfg.trading.defaultPlatform,
}

export const modeArg = {
  type: "string" as const,
  description: "Trade mode (shares, spreadbet)",
  alias: "m",
  default: cfg.trading.defaultMode,
}

export const accountArg = {
  type: "string" as const,
  description: "Account balance in GBP",
  alias: "a",
  default: String(cfg.trading.defaultAccountBalance),
}

export const riskArg = {
  type: "string" as const,
  description: "Risk per trade as decimal (e.g., 0.02 for 2%)",
  alias: "r",
  default: String(cfg.trading.defaultRiskPerTrade),
}

export const entryArg = {
  type: "string" as const,
  description: "Manual entry price override",
  alias: "e",
}
