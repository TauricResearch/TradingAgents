#!/usr/bin/env bun

/**
 * Execute trade plan via IG API.
 *
 * Calculates a trade plan (same as `trading plan`), validates against
 * IG instrument rules, places the order, and records it.
 *
 * Usage:
 *   trading execute AAPL
 *   trading execute AAPL --account 50000 --risk 0.02
 *   trading execute AAPL --yes --dry-run  # validate without executing
 *   trading execute AAPL --analysis-id <uuid>  # link to analysis
 */

import { DatabaseFactory } from "@lib/db"
import { defineCommand } from "citty"
import { IGClient } from "../../lib/ig-client.ts"
import { calculateTradePlan, type PriceBar } from "../../lib/trade-calculator.ts"
import {
  accountArg,
  analysisIdArg,
  dryRunArg,
  entryArg,
  modeArg,
  platformArg,
  riskArg,
  tickerArg,
  yesArg,
} from "../lib/args.ts"
import { getIGInstrument, validateIGPlan } from "../lib/ig-instruments.ts"
import { getPlatform, type TradeMode, validateMode } from "../lib/platforms.ts"

function getIGClient(): IGClient {
  const apiKey = process.env.IG_DEMO_API_KEY
  const username = process.env.IG_DEMO_USERNAME
  const password = process.env.IG_DEMO_PASSWORD
  if (!apiKey || !username || !password) {
    console.error("Missing IG credentials. Set IG_DEMO_API_KEY, IG_DEMO_USERNAME, IG_DEMO_PASSWORD")
    process.exit(1)
  }
  return new IGClient({
    apiKey,
    username,
    password,
    baseUrl: "https://demo-api.ig.com/gateway/deal",
  })
}

function fetchPriceHistory(ticker: string): PriceBar[] {
  const dbPath = process.env.PORTFOLIO_DB ?? "./portfolio.db"
  DatabaseFactory.connect(dbPath)
  const db = DatabaseFactory.get()

  const rows = db
    .query(
      `SELECT date, open, high, low, close, volume
       FROM prices
       WHERE ticker = ?
       ORDER BY date ASC`,
    )
    .all(ticker) as Array<{
    date: string
    open: number | string
    high: number | string
    low: number | string
    close: number | string
    volume: number | string
  }>

  if (rows.length === 0) {
    throw new Error(`No price history for ${ticker}. Run: trading sync --ticker ${ticker}`)
  }

  return rows.map((r) => ({
    date: r.date,
    open: parseFloat(String(r.open)),
    high: parseFloat(String(r.high)),
    low: parseFloat(String(r.low)),
    close: parseFloat(String(r.close)),
    volume: parseInt(String(r.volume), 10),
  }))
}

function fmt(n: number): string {
  return n.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function printPlan(plan: ReturnType<typeof calculateTradePlan>): void {
  console.log(`Ticker:          ${plan.ticker}`)
  console.log(`Entry:           $${fmt(plan.entry)}`)
  console.log(`Stop Loss:       $${fmt(plan.stopLoss)}`)
  console.log(`Target 1:        $${fmt(plan.target1)}`)
  console.log(`Target 2:        $${fmt(plan.target2)}`)
  console.log(`Position Size:   ${plan.positionSize}`)
  console.log(`ATR-14:          ${fmt(plan.atr14)}`)
  console.log(`Confidence:      ${plan.confidenceLevel}`)
  const stopPts = Math.max(1, Math.round(plan.entry - plan.stopLoss))
  const limitPts = Math.max(1, Math.round(plan.target1 - plan.entry))
  console.log(`Stop Distance:   ${stopPts} points`)
  console.log(`Limit Distance: ${limitPts} points`)
}

export const executeCommand = defineCommand({
  meta: {
    name: "execute",
    description: "Calculate trade plan and execute via IG API",
  },
  args: {
    ticker: tickerArg,
    platform: platformArg,
    mode: modeArg,
    account: accountArg,
    risk: riskArg,
    entry: entryArg,
    yes: yesArg,
    "dry-run": dryRunArg,
    "analysis-id": analysisIdArg,
  },
  run: async ({ args }) => {
    const ticker = args.ticker
    const platformName = args.platform
    const mode = args.mode as TradeMode
    const accountBalance = parseFloat(args.account)
    const riskPerTrade = parseFloat(args.risk)
    const entryPrice = args.entry ? parseFloat(args.entry) : undefined
    const yes = args.yes as boolean
    const dryRun = (args["dry-run"] as boolean) ?? false
    const analysisId = args["analysis-id"] as string | undefined

    // 1. Validate platform
    const platform = getPlatform(platformName)
    if (!platform) {
      console.error(`❌ Unknown platform: ${platformName}`)
      process.exit(1)
    }

    // 2. Validate mode
    const validation = validateMode(platformName, mode)
    if (!validation.ok) {
      console.error(`❌ ${validation.error}`)
      process.exit(1)
    }

    // 3. Only IG supported for execution
    if (platformName !== "ig") {
      console.error(`❌ Execution only supported for IG. Platform: ${platformName}`)
      console.error(`   Use 'trading plan ${ticker} --platform ${platformName}' for planning only.`)
      process.exit(1)
    }

    // 4. Fetch data
    let history: PriceBar[]
    try {
      history = fetchPriceHistory(ticker)
    } catch (e) {
      console.error(`❌ ${e instanceof Error ? e.message : String(e)}`)
      process.exit(1)
    }

    // 5. Calculate plan
    const plan = calculateTradePlan({
      ticker,
      priceHistory: history,
      accountBalance,
      riskPerTrade,
      entryPrice,
    })

    // 6. IG instrument validation (warnings only, non-fatal)
    const instrument = getIGInstrument(ticker)
    if (instrument) {
      const igValidation = validateIGPlan(plan, mode)
      if (igValidation.warnings.length > 0) {
        console.warn(`⚠️  IG validation warnings:`)
        for (const w of igValidation.warnings) {
          console.warn(`   ${w}`)
        }
      }
    }

    // 7a. Dry-run: validate with IG but do not execute
    if (dryRun) {
      console.log(`\n=== Dry Run: ${ticker} ===`)
      printPlan(plan)

      if (plan.concentrationFlag) {
        console.warn(`⚠️  Position exceeds 5% of portfolio`)
      }

      // IG instrument validation (no order placement)
      const igWarnings = instrument ? validateIGPlan(plan, mode).warnings : []
      if (igWarnings.length > 0) {
        console.warn(`⚠️  IG validation warnings:`)
        for (const w of igWarnings) console.warn(`   ${w}`)
      }

      console.log(`\nDry run complete. No order placed.`)
      return
    }

    // 7b. Display plan
    console.log(`\n=== Trade Plan ===`)
    printPlan(plan)

    if (plan.concentrationFlag) {
      console.warn(`⚠️  Position exceeds 5% of portfolio`)
    }

    // 8. Confirm execution (skip if --yes)
    if (!yes) {
      process.stdout.write(`\nExecute this trade on IG? [y/N] `)
      const answer = await new Promise<string>((resolve) => {
        process.stdin.once("data", (data: Buffer) => {
          resolve(data.toString().trim().toLowerCase())
        })
      })

      if (answer !== "y" && answer !== "yes") {
        console.log("Aborted.")
        process.exit(0)
      }
    } else {
      console.log(`\nExecuting (--yes specified)...`)
    }

    // 9. Authenticate with IG
    console.log(`Authenticating with IG...`)
    const client = getIGClient()
    const session = await client.login()
    console.log(`  Logged in: ${session.clientId}`)

    // Set preferred account
    const accounts = await client.getAccounts()
    const preferred = accounts.accounts.find((a) => a.preferred)
    if (preferred) {
      client.setAccountId(preferred.accountId)
      console.log(`  Account: ${preferred.accountId} (${preferred.accountType})`)
    }

    // 10. Place order
    const epic = instrument?.epic ?? ticker
    const isSpreadBet = mode === "spreadbet"
    const size = isSpreadBet ? plan.positionSize : Math.round(plan.positionSize)

    // Use plan values for stop/limit distances
    const stopDistance = Math.max(1, Math.round(plan.entry - plan.stopLoss))
    const limitDistance = Math.max(1, Math.round(plan.target1 - plan.entry))

    console.log(
      `\nPlacing ${mode} order: ${epic} | size: ${size} | stop: ${stopDistance} | limit: ${limitDistance}`,
    )

    const order = await client.createPosition({
      epic,
      direction: "BUY",
      size,
      expiry: isSpreadBet ? "DFB" : "-",
      orderType: "MARKET",
      currencyCode: instrument?.currency ?? "GBP",
      forceOpen: true,
      guaranteedStop: false,
      stopDistance,
      limitDistance,
    })

    console.log(`  Order ref: ${order.dealReference}`)

    // 11. Confirm
    const confirmation = await client.confirmTrade(order.dealReference)
    console.log(`  Status: ${confirmation.dealStatus}`)

    if (confirmation.dealStatus === "ACCEPTED") {
      console.log(`  Deal ID: ${confirmation.dealId}`)
      console.log(`  Level: ${confirmation.level}`)
      console.log(`  Size: ${confirmation.size}`)

      // 12. Record in database
      const dbPath = process.env.PORTFOLIO_DB ?? "./portfolio.db"
      DatabaseFactory.connect(dbPath)
      const db = DatabaseFactory.get()

      db.query(
        `INSERT INTO trades (ticker, action, quantity, price, date, reason, fees, analysis_id)
         VALUES (?, ?, ?, ?, date('now'), ?, ?, ?)`,
        [
          ticker,
          "buy",
          Math.round(size),
          plan.entry,
          `IG order: ${confirmation.dealId} | stop: ${plan.stopLoss} | target: ${plan.target1}`,
          0,
          analysisId ?? null,
        ],
      )
      console.log(`  Recorded in database${analysisId ? ` (linked to ${analysisId})` : ""}`)

      console.log(`\n✅ Trade executed: ${confirmation.dealId}`)
    } else {
      console.error(
        `\n❌ Trade rejected: ${(confirmation as Record<string, unknown>).reason ?? "unknown"}`,
      )
      process.exit(1)
    }
  },
})
