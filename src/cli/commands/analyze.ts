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
import { venvPython } from "../../server/lib/subprocess.ts"
import { dryRunArg, quietArg, verboseArg, yesArg } from "../lib/args.ts"
import { cliLogger, setLogLevel } from "../lib/cli-logger.ts"

// Default timeout matching SSE idleTimeout in server routes
const DEFAULT_TIMEOUT_S = 300

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

async function runAnalysis(
  ticker: string,
  debrief: boolean,
  timeout: number = DEFAULT_TIMEOUT_S,
): Promise<string> {
  const script = join(process.cwd(), "scripts", "py", "analyze_stream.py")

  if (!existsSync(script)) {
    throw new Error(`analyze_stream.py not found at ${script}`)
  }

  const env = {
    ...process.env,
    PYTHONUNBUFFERED: "1",
  }

  const flags: string[] = [ticker, "--timeout", String(timeout), "--heartbeat-interval", "15"]
  if (debrief) flags.push("--debrief")

  process.stdout.write(`🧠 Starting TradingAgents analysis for ${ticker}...\n`)

  const abortController = new AbortController()
  const timeoutId = setTimeout(() => {
    abortController.abort()
  }, timeout * 1000)

  const proc = Bun.spawn([venvPython(), script, ...flags], {
    stdout: "pipe",
    stderr: "pipe",
    env,
    signal: abortController.signal,
  })

  const decoder = new TextDecoder()
  const chunks: string[] = []

  // Read stdout and stderr concurrently for live heartbeat updates
  const stdoutPromise = (async () => {
    for await (const chunk of proc.stdout) {
      const text = decoder.decode(chunk)
      process.stdout.write(text)
      chunks.push(text)
    }
  })()

  const stderrPromise = (async () => {
    for await (const chunk of proc.stderr) {
      const text = decoder.decode(chunk)
      // stderr contains heartbeat events — parse and display as progress
      for (const line of text.split("\n")) {
        const trimmed = line.trim()
        if (!trimmed?.startsWith("{")) continue
        try {
          const parsed = JSON.parse(trimmed)
          if (parsed.event === "heartbeat") {
            process.stdout.write(`\r   🫀 heartbeat tick ${parsed.data.tick}...`)
          }
        } catch {
          // Non-JSON stderr — forward as warning
          process.stderr.write(`${trimmed}\n`)
        }
      }
    }
  })()

  try {
    await Promise.all(stdoutPromise, stderrPromise)
  } finally {
    clearTimeout(timeoutId)
  }

  const exitCode = await proc.exited
  if (exitCode !== 0) {
    cliLogger.error("Analysis failed with non-zero exit code", { exitCode, ticker })
    throw new Error(`Analysis failed with exit code ${exitCode}`)
  }
  cliLogger.info("Analysis completed successfully", { ticker })

  // Clear the heartbeat progress line
  if (chunks.length > 0) process.stdout.write("\n")

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

  cliLogger.debug("Running execute command", { ticker, analysisId, dryRun })
  process.stdout.write("\n")
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
    quiet: quietArg,
    verbose: verboseArg,
  },
  run: async ({ args }) => {
    // Apply log level from --quiet/--verbose flags
    const logLevel = (args.quiet as boolean)
      ? "quiet"
      : (args.verbose as boolean)
        ? "verbose"
        : undefined
    setLogLevel(logLevel)

    const ticker = args.ticker
    const executeAfter = args.execute as boolean
    const yes = args.yes as boolean
    const dryRun = (args["dry-run"] as boolean) ?? false

    cliLogger.debug("Starting analysis", { ticker, logLevel })

    // Generate a stable analysis ID for this run
    const analysisId = `${ticker.toUpperCase()}-${Date.now()}`

    // Run analysis
    const stdout = await runAnalysis(ticker, args.debrief as boolean)
    cliLogger.info("Analysis complete", { ticker })
    process.stdout.write(`\n✓ Analysis complete for ${ticker}\n`)

    // Parse decision
    const decision = parseDecisionEvents(stdout)
    if (decision) {
      cliLogger.info("Decision parsed", {
        signal: decision.signal,
        confidence: decision.confidence,
      })
      process.stdout.write(
        `\n📊 Decision: ${decision.signal.toUpperCase()} (confidence: ${(decision.confidence * 100).toFixed(0)}%)\n`,
      )
      if (decision.reasoning) {
        const preview = decision.reasoning.slice(0, 200).replace(/\n/g, " ").trim()
        process.stdout.write(`   ${preview}...\n`)
      }
    } else {
      cliLogger.warn("Could not parse decision from analysis output", { ticker })
      process.stdout.write(`\n⚠️  Could not parse decision from analysis output\n`)
    }

    // Execute if requested
    if (executeAfter) {
      if (!decision) {
        cliLogger.error("Cannot execute: no decision parsed", { ticker })
        process.stdout.write(
          `\n❌ Cannot execute: no decision parsed from analysis. Run 'trading execute ${ticker}' manually.\n`,
        )
        process.exit(1)
      }

      const signal = decision.signal.toLowerCase()
      if (signal !== "buy" && signal !== "sell") {
        cliLogger.info("Decision not actionable for execution", { signal, ticker })
        process.stdout.write(`\n→ Decision was '${signal}', skipping execution.\n`)
        process.stdout.write(`   Run 'trading execute ${ticker}' manually to force execution.\n`)
        process.exit(0)
      }

      // Execute
      const exitCode = await runExecute(ticker, analysisId, yes, dryRun)
      process.exit(exitCode)
    }
  },
})
