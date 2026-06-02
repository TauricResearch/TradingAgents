#!/usr/bin/env bun

/**
 * Scan — evaluate technical indicator entry gates and exit triggers.
 *
 * Usage:
 *   trading scan                   # scan SPY, QQQ, IWM
 *   trading scan AAPL             # scan single ticker
 *   trading scan SPY QQQ          # scan multiple tickers
 *   trading scan SPY --relax=rsi  # relax RSI gate
 *   trading scan --json           # machine-readable JSON output
 *   trading scan --plain          # suppress gum, plain ANSI
 */

import { DatabaseFactory } from "@lib/db"
import { cfg } from "@lib/settings"
import { defineCommand } from "citty"
import {
  computeSnapshot,
  evaluateScan,
  type GateName,
  type OHLCVBar,
  type ScanResult,
} from "../../server/lib/indicators.ts"
import { isGumAvailable } from "../lib/gum-utils"

// ── Colors (plain ANSI when gum unavailable) ─────────────────────────────────

function color(text: string, code: string): string {
  return `${code}${text}\x1b[0m`
}

function green(text: string) {
  return color(text, "\x1b[32m")
}

function red(text: string) {
  return color(text, "\x1b[32m") // red
}

function yellow(text: string) {
  return color(text, "\x1b[33m")
}

function cyan(text: string) {
  return color(text, "\x1b[36m")
}

function dim(text: string) {
  return color(text, "\x1b[2m")
}

// ── Default tickers ──────────────────────────────────────────────────────────

const DEFAULT_TICKERS = ["SPY", "QQQ", "IWM"]

const VALID_GATES: GateName[] = ["rsi", "bollinger", "ma20", "adx", "macd", "volume"]

// ── DB helpers ───────────────────────────────────────────────────────────────

interface PriceRow {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

function getPriceHistory(ticker: string): OHLCVBar[] {
  const db = DatabaseFactory.get()
  const rows = db
    .query(
      "SELECT date, open, high, low, close, volume FROM prices WHERE ticker = ? ORDER BY date ASC",
    )
    .all(ticker) as PriceRow[]

  return rows.map((r) => ({
    date: r.date,
    open: parseFloat(String(r.open)),
    high: parseFloat(String(r.high)),
    low: parseFloat(String(r.low)),
    close: parseFloat(String(r.close)),
    volume: parseFloat(String(r.volume)),
  }))
}

// ── Output formatters ────────────────────────────────────────────────────────

function _formatGatesPlain(result: ScanResult): string[] {
  const lines: string[] = []

  for (const gate of result.gates) {
    const icon = gate.relaxed ? dim("~") : gate.pass ? green("✓") : red("✗")
    const valueStr =
      gate.value !== null && !Number.isNaN(gate.value) ? formatValue(gate.value) : "—"
    const relaxedTag = gate.relaxed ? dim(" [relaxed]") : ""
    lines.push(`${icon} ${gate.threshold.padEnd(28)} ${valueStr}${relaxedTag}`)
  }

  return lines
}

function _formatGatesJson(result: ScanResult): object {
  return {
    name: result.gates[0]?.name ?? "unknown",
    pass: result.gates[0]?.pass ?? false,
    value: result.gates[0]?.value,
    threshold: result.gates[0]?.threshold ?? "",
    relaxed: result.gates[0]?.relaxed ?? false,
  }
}

function formatValue(value: number): string {
  if (Math.abs(value) >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`
  }
  if (Math.abs(value) >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`
  }
  if (Math.abs(value) >= 100) {
    return value.toFixed(1)
  }
  if (Math.abs(value) >= 1) {
    return value.toFixed(2)
  }
  return value.toFixed(4)
}

function _formatVolume(volume: number): string {
  if (Number.isNaN(volume)) return "—"
  if (volume >= 1_000_000) return `${(volume / 1_000_000).toFixed(1)}M`
  if (volume >= 1_000) return `${(volume / 1_000).toFixed(0)}K`
  return volume.toFixed(0)
}

function scanOneTicker(
  ticker: string,
  relaxedGates: Set<GateName>,
  _asJson: boolean,
): ScanResult | { error: string; detail: string; hint: string } {
  try {
    const bars = getPriceHistory(ticker)

    if (bars.length < 150) {
      return {
        error: `Insufficient price history for ${ticker}`,
        detail: `${bars.length} bars (need ≥150 for MA150)`,
        hint: `Sync prices first: trading prices sync --ticker ${ticker}`,
      }
    }

    const snapshot = computeSnapshot(ticker, bars)
    if (!snapshot) {
      return {
        error: `computeSnapshot returned null for ${ticker}`,
        detail: "Likely insufficient bars",
        hint: "Ensure >= 150 bars of data",
      }
    }

    const result = evaluateScan(ticker, snapshot, relaxedGates)
    return result
  } catch (err) {
    return {
      error: `Failed to scan ${ticker}`,
      detail: String(err),
      hint: "Check DB connection and data availability",
    }
  }
}

function outputPlain(ticker: string, result: ScanResult): void {
  const _hasGum = isGumAvailable()

  console.log("")
  console.log(cyan(`=== SCAN: ${ticker} ===`))
  console.log(
    `${"Date:".padEnd(12)} ${result.date}  |  ${"Price:".padEnd(8)} ${result.price.toFixed(2)}`,
  )
  console.log("")

  // Gate results
  for (const gate of result.gates) {
    const icon = gate.relaxed ? dim("~") : gate.pass ? green("✓") : red("✗")
    const valueStr =
      gate.value !== null && !Number.isNaN(gate.value) ? formatValue(gate.value) : "—"
    const relaxedTag = gate.relaxed ? dim(" [relaxed]") : ""
    console.log(`${icon} ${gate.threshold.padEnd(28)} ${valueStr}${relaxedTag}`)
  }

  console.log("")

  // MA150 filter
  const ma150Icon = result.ma150Passed ? green("✓") : red("✗")
  const ma150Val = result.snapshot?.ma_150 ? formatValue(result.snapshot.ma_150) : "—"
  console.log(`${ma150Icon} ${"150-day MA filter".padEnd(28)} ${ma150Val}`)

  console.log("")

  // Signal
  let signalStr: string
  let signalColor: (t: string) => string
  if (result.signal === "buy") {
    signalStr = "BUY"
    signalColor = green
  } else if (result.signal === "sell") {
    signalStr = "SELL"
    signalColor = red
  } else {
    signalStr = "NO-BUY"
    signalColor = yellow
  }

  const reason =
    result.signal === "buy"
      ? "all gates passed"
      : result.signal === "sell"
        ? (result.exitTriggers[0] ?? "exit trigger")
        : "gate failed"

  console.log(`${"Signal:".padEnd(12)} ${signalColor(signalStr.padEnd(8))} ${dim(`(${reason})`)}`)

  // Exit triggers
  if (result.exitTriggers.length > 0) {
    console.log(`${"Exit:".padEnd(12)} ${red(result.exitTriggers.join(", "))}`)
  } else {
    console.log(`${"Exit:".padEnd(12)} ${dim("clear (no triggers)")}`)
  }

  console.log("")
}

function _outputJson(result: ScanResult): void {
  const output = {
    ticker: result.ticker,
    date: result.date,
    price: result.price,
    signal: result.signal,
    gates: result.gates.map((g) => ({
      name: g.name,
      pass: g.pass,
      value: g.value,
      relaxed: g.relaxed,
    })),
    gatesPassed: result.gatesPassed,
    gatesTotal: result.gatesTotal,
    ma150: {
      passed: result.ma150Passed,
      value: result.snapshot?.ma_150 ?? null,
    },
    exitTriggers: result.exitTriggers,
    snapshot:
      result.snapshot !== null
        ? {
            rsi_14: result.snapshot.rsi_14,
            bb_lower: result.snapshot.bb_lower,
            bb_middle: result.snapshot.bb_middle,
            bb_upper: result.snapshot.bb_upper,
            ma_20: result.snapshot.ma_20,
            ma_150: result.snapshot.ma_150,
            adx_14: result.snapshot.adx_14,
            macd_line: result.snapshot.macd_line,
            macd_signal: result.snapshot.macd_signal,
            macd_histogram: result.snapshot.macd_histogram,
            volume: result.snapshot.volume,
            volume_20avg: result.snapshot.volume_20avg,
          }
        : null,
  }

  console.log(JSON.stringify(output, null, 2))
}

function outputError(ticker: string, err: { error: string; detail: string; hint: string }): void {
  const errorObj = { ticker, error: err.error, detail: err.detail, hint: err.hint }
  console.error(JSON.stringify(errorObj, null, 2))
}

// ── Command ─────────────────────────────────────────────────────────────────

export const scanCommand = defineCommand({
  meta: {
    name: "scan",
    description: "Evaluate technical indicator entry gates and exit triggers",
  },
  args: {
    "<tickers>": {
      type: "positional",
      description: "Ticker symbols (default: SPY, QQQ, IWM)",
      required: false,
      default: DEFAULT_TICKERS.join(" "),
    },
    "--relax": {
      type: "string",
      description: "Relax a gate (rsi, bollinger, ma20, adx, macd, volume). Repeat for multiple.",
    },
    "--json": {
      type: "boolean",
      description: "Machine-readable JSON output",
    },
    "--plain": {
      type: "boolean",
      description: "Suppress gum, use plain ANSI",
    },
    "--no-store": {
      type: "boolean",
      description: "Skip DB writes (indicator_readings, scan_history)",
    },
  },
  run: async (ctx) => {
    // Parse tickers
    const rawTickers = ctx.args.tickers as string | undefined
    const tickers = rawTickers
      ? rawTickers
          .split(/\s+/)
          .map((t) => t.trim().toUpperCase())
          .filter((t) => t.length > 0)
      : DEFAULT_TICKERS

    if (tickers.length === 0) {
      console.error(
        JSON.stringify({
          error: "No tickers provided",
          hint: "Provide ticker symbols or use defaults",
        }),
      )
      process.exit(1)
    }

    // Parse relax flags
    const relaxedGates = new Set<GateName>()
    const relaxArg = ctx.args.relax as string | undefined
    if (relaxArg) {
      for (const gateName of relaxArg.split(",").map((g) => g.trim().toLowerCase())) {
        if (VALID_GATES.includes(gateName as GateName)) {
          relaxedGates.add(gateName as GateName)
        } else {
          console.error(
            JSON.stringify({
              error: `Unknown gate: ${gateName}`,
              detail: `Valid gates: ${VALID_GATES.join(", ")}`,
              hint: "Use --relax=rsi or --relax=rsi,macd for multiple",
            }),
          )
          process.exit(1)
        }
      }
    }

    const asJson = (ctx.args.json as boolean) ?? false
    const noStore = (ctx.args["no-store"] as boolean) ?? false

    // Connect to DB (only if storing)
    if (!noStore) {
      DatabaseFactory.connect(cfg.portfolio.db)
    }

    // Scan each ticker
    if (asJson) {
      const results: object[] = []
      for (const ticker of tickers) {
        const result = scanOneTicker(ticker, relaxedGates, asJson)
        if ("error" in result) {
          results.push({ ticker, ...result })
        } else {
          if (!noStore) storeResult(result)
          results.push({
            ticker: result.ticker,
            date: result.date,
            price: result.price,
            signal: result.signal,
            gates: result.gates.map((g) => ({
              name: g.name,
              pass: g.pass,
              value: g.value,
              relaxed: g.relaxed,
            })),
            gatesPassed: result.gatesPassed,
            gatesTotal: result.gatesTotal,
            ma150: {
              passed: result.ma150Passed,
              value: result.snapshot?.ma_150 ?? null,
            },
            exitTriggers: result.exitTriggers,
          })
        }
      }
      console.log(JSON.stringify({ scans: results }, null, 2))
    } else {
      // Plain text output
      let hasErrors = false
      for (const ticker of tickers) {
        const result = scanOneTicker(ticker, relaxedGates, asJson)
        if ("error" in result) {
          outputError(ticker, result)
          hasErrors = true
        } else {
          if (!noStore) storeResult(result)
          outputPlain(ticker, result)
        }
      }

      if (hasErrors) {
        process.exit(1)
      }
    }
  },
})

// ── DB write helpers ─────────────────────────────────────────────────────────

function storeResult(result: ScanResult): void {
  if (!result.snapshot) return

  const snap = result.snapshot
  const db = DatabaseFactory.get()

  // Upsert indicator_readings (one row per ticker-date)
  db.execute(
    `INSERT INTO indicator_readings
       (ticker, date, price, rsi_14, bb_lower, bb_middle, bb_upper,
        ma_20, ma_150, adx_14, macd_line, macd_signal, macd_histogram,
        volume, volume_20avg, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
     ON CONFLICT(ticker, date) DO UPDATE SET
       price = excluded.price,
       rsi_14 = excluded.rsi_14,
       bb_lower = excluded.bb_lower,
       bb_middle = excluded.bb_middle,
       bb_upper = excluded.bb_upper,
       ma_20 = excluded.ma_20,
       ma_150 = excluded.ma_150,
       adx_14 = excluded.adx_14,
       macd_line = excluded.macd_line,
       macd_signal = excluded.macd_signal,
       macd_histogram = excluded.macd_histogram,
       volume = excluded.volume,
       volume_20avg = excluded.volume_20avg,
       created_at = datetime('now')`,
    [
      snap.ticker,
      snap.date,
      snap.price,
      snap.rsi_14,
      snap.bb_lower,
      snap.bb_middle,
      snap.bb_upper,
      snap.ma_20,
      snap.ma_150,
      snap.adx_14,
      snap.macd_line,
      snap.macd_signal,
      snap.macd_histogram,
      snap.volume,
      snap.volume_20avg,
    ],
  )

  // Append scan_history (one row per scan result)
  db.execute(
    `INSERT INTO scan_history (ticker, date, gates_passed, gates_total, signal, exit_trigger)
     VALUES (?, ?, ?, ?, ?, ?)`,
    [
      result.ticker,
      result.date,
      result.gatesPassed,
      result.gatesTotal,
      result.signal,
      result.exitTriggers[0] ?? null,
    ],
  )
}
