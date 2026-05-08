#!/usr/bin/env bun
/**
 * Generate LLM summary for analyses.
 *
 * Delegates to scripts/summarize_analyses.ts
 * Usage: trading summarize [TICKER]
 */

import { defineCommand } from "citty"

export const summarizeCommand = defineCommand({
  meta: { name: "summarize", description: "Generate LLM summary for analyses" },
  args: {
    ticker: {
      type: "positional",
      description: "Ticker to summarize (default: all)",
    },
  },
  run: async ({ args }) => {
    const flags: string[] = []
    if (args.ticker) flags.push("--ticker", args.ticker)

    const proc = Bun.spawn(["bun", "scripts/summarize_analyses.ts", ...flags], {
      stdout: "inherit",
      stderr: "inherit",
    })

    const exitCode = await proc.exited
    if (exitCode !== 0) {
      process.exit(exitCode)
    }
  },
})
