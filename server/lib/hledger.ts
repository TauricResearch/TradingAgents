/**
 * hLedger integration — read-only wrapper.
 *
 * hLedger owns the accounting data (transactions, prices, balances).
 * This module spawns hledger and parses its JSON output into clean
 * holdings that the dashboard can display.
 *
 * Commodities with dots (e.g. "TKA.DE") must be quoted in the journal:
 *   500 "TKA.DE"  and  P 2026-05-02 "TKA.DE" 9.20 EUR
 */

import { spawn } from "node:child_process"

const DEFAULT_JOURNAL = process.env.HLEDGER_FILE ?? `${process.env.HOME}/.hledger.journal`

interface HLAmount {
  aquantity: { floatingPoint: number }
  acommodity: string
  acost?: {
    contents: {
      aquantity: { floatingPoint: number }
      acommodity: string
    }
  }
}

interface HLBalanceRow {
  0: string // full account name
  1: string // short name
  2: number // depth
  3: HLAmount[]
}

export interface HLHolding {
  ticker: string
  quantity: number
  costBasis: number // total cost in EUR
  costPerShare: number // average cost per share
  platform: string // e.g. "degiero", "pension:nn", "test"
}

export interface HLCashBalance {
  currency: string
  amount: number
  platform: string
}

export interface PlatformSummary {
  name: string
  totalValue: number
  cash: number
  holdings: number
  holdingCount: number
}

export interface HLResult {
  holdings: HLHolding[]
  cash: HLCashBalance[]
  platforms: PlatformSummary[]
  errors?: string[]
}

function runHledger(args: string[], journal: string = DEFAULT_JOURNAL): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn("hledger", ["-f", journal, ...args], {
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    })

    let stdout = ""
    let stderr = ""

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString()
    })

    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString()
    })

    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`hledger exited with code ${code}: ${stderr.trim()}`))
        return
      }
      resolve(stdout)
    })

    child.on("error", reject)
  })
}

/**
 * Parse a hLedger balance --tree -O json output into holdings + cash.
 */
export function parseBalanceJson(raw: string): HLResult {
  const rows = JSON.parse(raw) as [HLBalanceRow[], HLAmount[]]
  const balanceRows = rows[0]
  const holdings: HLHolding[] = []
  const cash: HLCashBalance[] = []

  for (const row of balanceRows) {
    // Skip root (depth=0), platform aggregates (depth=1), and Equity/blank
    // Depth 1 rows (assets:degiero, assets:ibkr) aggregate cash+holdings into one
    // entry with 2 path segments — extractPlatform returns "unknown" for those.
    // Only process depth >= 2: assets:platform:cash and assets:platform:holdings.
    if (row[0].startsWith("Equity") || row[0] === "" || row[2] <= 1) continue

    const platform = extractPlatform(row[0])

    for (const amt of row[3]) {
      const qty = amt.aquantity.floatingPoint
      const commodity = amt.acommodity

      // Skip zero balances
      if (qty === 0) continue

      // Cash accounts (EUR, USD, GBP, etc.)
      if (isCurrency(commodity)) {
        cash.push({ currency: commodity, amount: qty, platform })
        continue
      }

      // Holdings (stocks, ETFs, crypto)
      const costBasis = amt.acost?.contents.aquantity.floatingPoint ?? 0
      const costPerShare = qty !== 0 ? costBasis / qty : 0

      holdings.push({
        ticker: commodity.replace(/^"|"$/g, ""), // strip quotes
        quantity: qty,
        costBasis,
        costPerShare,
        platform,
      })
    }
  }

  return { holdings, cash, platforms: buildPlatformSummaries(holdings, cash) }
}

/**
 * Extract platform name from an hLedger account path.
 *
 * Convention: assets:<platform>:<account_type>
 *   assets:degiero:cash         → platform = "degiero"
 *   assets:pension:nn:cash     → platform = "pension:nn"
 *   assets:test:holdings       → platform = "test"
 *
 * Platform = everything between "assets:" and the last segment.
 */
function extractPlatform(accountPath: string): string {
  const parts = accountPath.split(":")
  // Remove "assets" (first) and account type (last)
  const platformParts = parts.slice(1, -1)
  if (platformParts.length === 0) return "unknown"
  return platformParts.join(":")
}

/**
 * Build per-platform summary from holdings and cash.
 */
function buildPlatformSummaries(holdings: HLHolding[], cash: HLCashBalance[]): PlatformSummary[] {
  const map = new Map<string, { cash: number; holdings: number; count: number }>()

  for (const c of cash) {
    const s = map.get(c.platform) ?? { cash: 0, holdings: 0, count: 0 }
    s.cash += c.amount
    map.set(c.platform, s)
  }

  for (const h of holdings) {
    const s = map.get(h.platform) ?? { cash: 0, holdings: 0, count: 0 }
    s.holdings += h.costBasis
    s.count += 1
    map.set(h.platform, s)
  }

  const summaries: PlatformSummary[] = []
  for (const [name, s] of map) {
    summaries.push({
      name,
      totalValue: s.cash + s.holdings,
      cash: s.cash,
      holdings: s.holdings,
      holdingCount: s.count,
    })
  }
  // Sort: real platforms first (not "test"), then by total value descending
  summaries.sort((a, b) => {
    if (a.name === "test") return 1
    if (b.name === "test") return -1
    return b.totalValue - a.totalValue
  })
  return summaries
}

function isCurrency(c: string): boolean {
  return ["EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD", "SEK", "NOK", "DKK"].includes(
    c.replace(/^"|"$/g, ""),
  )
}

/**
 * Get current holdings from hLedger.
 */
export async function getHoldings(journal?: string): Promise<HLResult> {
  const raw = await runHledger(["balance", "--tree", "-O", "json"], journal)
  return parseBalanceJson(raw)
}

/**
 * Get price history from hLedger.
 * Returns array of { date, ticker, price, currency }
 */
export async function getPrices(
  journal?: string,
): Promise<Array<{ date: string; ticker: string; price: number; currency: string }>> {
  const raw = await runHledger(["prices", "-O", "json"], journal)
  const entries = JSON.parse(raw) as Array<{
    pdate: string
    pcommodity: string
    pprice: { aquantity: { floatingPoint: number }; acommodity: string }
  }>

  return entries.map((e) => ({
    date: e.pdate,
    ticker: e.pcommodity.replace(/^"|"$/g, ""),
    price: e.pprice.aquantity.floatingPoint,
    currency: e.pprice.acommodity,
  }))
}

/**
 * Get allocation tree (market value by account).
 */
export async function getAllocation(journal?: string): Promise<string> {
  return runHledger(["balance", "--tree", "--value", "end", "--depth", "3"], journal)
}
