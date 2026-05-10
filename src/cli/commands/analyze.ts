#!/usr/bin/env bun
/**
 * Run TradingAgents analysis for a ticker.
 *
 * Usage:
 *   trading analyze <ticker>
 *   trading analyze <ticker> --execute        # run execute after analysis
 *   trading analyze <ticker> --execute --yes  # execute without prompting
 *   trading analyze <ticker> --dry-run        # show plan without executing
 */

import { existsSync } from "node:fs"
import { join } from "node:path"
import { defineCommand } from "citty"
import { dryRunArg, yesArg } from "../lib/args.ts"

interface DecisionEvent {
  signal: string
  reasoning: string
  confidence: number
}

function parseDecisionEvents(stdout: string): DecisionEvent | null {
  for (const line of stdout.split("\n")) {
    const trimmed = line.trim()
    if (!trimmed?.startsWith("{")) continue
    try {
      const parsed = JSON.parse(trimmed)
      if (parsed.event === "decision" && parsed.data) {
        return {
          signal: parsed.data.signal ?? "hold",
          reasoning: parsed.data.reasoning ?? "",
          confidence: parsed.data.confidence ?? 0.5,
        }
      }
    } catch {
      // skip malformed lines
    }
  }
  return null
}

async function runAnalysis(ticker: string, debrief: boolean): Promise<string> {
  const script = join(process.cwd(), "scripts", "py", "analyze_stream.py")

  if (!existsSync(script)) {
    throw new Error(`analyze_stream.py not found at ${script}`)
  }

  const env = {
    ...process.env,
    PYTHONUNBUFFERED: "1",
  }

  const flags: string[] = [ticker]
  if (debrief) flags.push("--debrief")

  console.log(`🧠 Starting TradingAgents analysis for ${ticker}...`)

  const proc = Bun.spawn(["python3", script, ...flags], {
    stdout: "pipe",
    stderr: "pipe",
    env,
  })

  const decoder = new TextDecoder()
  const chunks: string[] = []

  for await (const chunk of proc.stdout) {
    const text = decoder.decode(chunk)
    process.stdout.write(text)
    chunks.push(text)
  }

  const stderr = decoder.decode(await proc.stderr)
  if (stderr.trim()) {
    console.error(stderr)
  }

  const exitCode = await proc.exited
  if (exitCode !== 0) {
    throw new Error(`Analysis failed with exit code ${exitCode}`)
  }

  return chunks.join("")
}

async function runExecute(
  ticker: string,
  analysisId: string,
  yes: boolean,
  dryRun: boolean,
): Promise<number> {
  const exe = join(process.cwd(), "src", "cli", "main.ts")
  const args = ["execute", ticker, "--analysis-id", analysisId]
  if (yes) args.push("--yes")
  if (dryRun) args.push("--dry-run")

  console.log("")
  const proc = Bun.spawn(["bun", exe, ...args], {
    stdout: "inherit",
    stderr: "inherit",
    stdin: "inherit",
  })

  return await proc.exited
}

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
    execute: {
      type: "boolean",
      description: "Run trading execute after analysis completes",
      default: false,
    },
    yes: yesArg,
    "dry-run": dryRunArg,
  },
  run: async ({ args }) => {
    const ticker = args.ticker
    const executeAfter = args.execute as boolean
    const yes = args.yes as boolean
    const dryRun = (args["dry-run"] as boolean) ?? false

    // Generate a stable analysis ID for this run
    const analysisId = `${ticker.toUpperCase()}-${Date.now()}`

    // Run analysis
    const stdout = await runAnalysis(ticker, args.debrief as boolean)
    console.log(`\n✓ Analysis complete for ${ticker}`)

    // Parse decision
    const decision = parseDecisionEvents(stdout)
    if (decision) {
      console.log(
        `\n📊 Decision: ${decision.signal.toUpperCase()} (confidence: ${(decision.confidence * 100).toFixed(0)}%)`,
      )
      if (decision.reasoning) {
        const preview = decision.reasoning.slice(0, 200).replace(/\n/g, " ").trim()
        console.log(`   ${preview}...`)
      }
    } else {
      console.warn(`\n⚠️  Could not parse decision from analysis output`)
    }

    // Execute if requested
    if (executeAfter) {
      if (!decision) {
        console.error(
          `❌ Cannot execute: no decision parsed from analysis. Run 'trading execute ${ticker}' manually.`,
        )
        process.exit(1)
      }

      const signal = decision.signal.toLowerCase()
      if (signal !== "buy" && signal !== "sell") {
        console.log(`\n→ Decision was '${signal}', skipping execution.`)
        console.log(`   Run 'trading execute ${ticker}' manually to force execution.`)
        process.exit(0)
      }

      // Execute
      const exitCode = await runExecute(ticker, analysisId, yes, dryRun)
      process.exit(exitCode)
    }
  },
})
