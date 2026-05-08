#!/usr/bin/env bun

/**
 * Run TradingAgents analysis for a ticker.
 *
 * Delegates to scripts/py/analyze_stream.py
 * Usage: trading analyze <ticker>
 */

import { existsSync } from "node:fs"
import { join } from "node:path"
import { defineCommand } from "citty"

export const analyzeCommand = defineCommand({
  meta: {
    name: "analyze",
    description: "Run TradingAgents LLM analysis for a ticker",
  },
  args: {
    ticker: {
      type: "positional",
      description: "Stock ticker to analyze (e.g. AAPL, TKA.DE)",
      required: true,
    },
    debrief: {
      type: "boolean",
      description: "Save output to debriefs/ directory",
      default: false,
    },
  },
  run: async ({ args }) => {
    const ticker = args.ticker
    const script = join(process.cwd(), "scripts", "py", "analyze_stream.py")

    if (!existsSync(script)) {
      console.error(`❌ Error: analyze_stream.py not found at ${script}`)
      process.exit(1)
    }

    const env = {
      ...process.env,
      PYTHONUNBUFFERED: "1",
    }

    const flags: string[] = [ticker]
    if (args.debrief) flags.push("--debrief")

    console.log(`🧠 Starting TradingAgents analysis for ${ticker}...`)
    console.log("")

    const proc = Bun.spawn(["python3", script, ...flags], {
      stdout: "inherit",
      stderr: "inherit",
      env,
    })

    const exitCode = await proc.exited
    if (exitCode !== 0) {
      console.error(`\n❌ Analysis failed with exit code ${exitCode}`)
      process.exit(exitCode)
    }

    console.log(`\n✓ Analysis complete for ${ticker}`)
  },
})
