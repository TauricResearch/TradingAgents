/**
 * Shared CLI argument definitions for citty commands.
 * Import and reuse across subcommands for consistency.
 *
 * Defaults cascade: args → config store → settings.ts → hardcoded.
 */

import { config } from "../../lib/config.ts"

export const tickerArg = {
  type: "positional" as const,
  description: "Stock ticker symbol (e.g., AAPL, TKA.DE)",
  required: true,
}

export const platformArg = {
  type: "string" as const,
  description: "Platform (ajbell, aviva, ig, nsandi)",
  alias: "p",
  default: config.get("platform", "ig"),
}

export const modeArg = {
  type: "string" as const,
  description: "Trade mode (shares, spreadbet)",
  alias: "m",
  default: config.get("mode", "shares"),
}

export const accountArg = {
  type: "string" as const,
  description: "Account balance in GBP",
  alias: "a",
  default: String(config.getNumber("account", 50000)),
}

export const riskArg = {
  type: "string" as const,
  description: "Risk per trade as decimal (e.g., 0.02 for 2%)",
  alias: "r",
  default: String(config.getNumber("risk", 0.02)),
}

export const entryArg = {
  type: "string" as const,
  description: "Manual entry price override",
  alias: "e",
}

export const yesArg = {
  type: "boolean" as const,
  description: "Skip confirmation prompt and execute immediately",
  alias: "y",
}

export const dryRunArg = {
  type: "boolean" as const,
  description: "Show plan + IG validation but do not place order",
}

export const analysisIdArg = {
  type: "string" as const,
  description: "Analysis UUID to link this execution to a prior analysis",
}
