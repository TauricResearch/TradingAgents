/**
 * Portfolio intelligence computation — aggregates positions, cash, and governance
 * into a unified PortfolioIntel response from SQLite + hledger data.
 */

import { DatabaseFactory } from "../../lib/db.ts"
import { checkRules, loadRules, suggestRebalance } from "./governance.ts"
import { getHoldings } from "./hledger.ts"
import { fetchPrices } from "./intel-prices.ts"
import {
  type AccountSummary,
  ALLOCATION_TARGETS,
  type AllocationBar,
  type AssetClassAllocation,
  type CashBalance,
  type CashBreakdown,
  type DbAccount,
  type DbPosition,
  type DbSpreadBet,
  type DbWatchlistItem,
  type PortfolioIntel,
  type PositionWithValue,
  type SpreadBetWithPnl,
} from "./intel-types.ts"

export function classifyTicker(ticker: string, exchange: string): string {
  const t = ticker.toUpperCase()
  if (t === "VWCE.DE" || t === "IWDA.L" || t === "CSPX.L" || t === "TERA.SW") return "etf"
  if (exchange === "CRYPTO" || ["BTC", "ETH", "SOL", "XRP"].includes(t)) return "crypto"
  return "equity"
}

export async function computePortfolioIntelligence(): Promise<PortfolioIntel> {
  const { cash: hlCash } = await getHoldings()

  const db = DatabaseFactory.get()

  // 1. Fetch accounts (parseFloat on REAL columns — SQLite returns strings)
  const rawAccounts = db.query("SELECT * FROM accounts").all() as DbAccount[]
  const accounts = rawAccounts.map((a) => ({ ...a, balance: parseFloat(String(a.balance)) }))
  const accountsById = new Map<string, DbAccount>(accounts.map((a) => [a.id, a]))

  // 2. Fetch positions with account linkage (parseFloat on REAL columns)
  const rawPositions = db
    .query(
      "SELECT id, ticker, exchange, platform, account_id, quantity, avg_cost, entry_date, thesis FROM positions WHERE status = 'open'",
    )
    .all() as DbPosition[]
  const dbPositions = rawPositions.map((p) => ({
    ...p,
    quantity: parseFloat(String(p.quantity)),
    avg_cost: parseFloat(String(p.avg_cost)),
  }))

  // 3. Fetch spread bet positions (parseFloat on REAL columns)
  const rawBets = db
    .query("SELECT * FROM spreadbet_positions WHERE status = 'open'")
    .all() as DbSpreadBet[]
  const dbBets = rawBets.map((b) => ({
    ...b,
    stake_per_point: parseFloat(String(b.stake_per_point)),
    entry_price: parseFloat(String(b.entry_price)),
    stop_price: b.stop_price != null ? parseFloat(String(b.stop_price)) : null,
    target_price: b.target_price != null ? parseFloat(String(b.target_price)) : null,
    current_price: b.current_price != null ? parseFloat(String(b.current_price)) : null,
    pnl_gbp: b.pnl_gbp != null ? parseFloat(String(b.pnl_gbp)) : null,
  }))

  // 4. Fetch research queue
  const researchQueue = db
    .query(
      "SELECT id, ticker, exchange, priority, thesis, added_date, last_signal FROM watchlist WHERE stage = 'approved' ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END",
    )
    .all() as DbWatchlistItem[]

  // 5. Fetch live prices
  const posTickers = [...new Set(dbPositions.map((p) => p.ticker))]
  const betTickers = [...new Set(dbBets.map((b) => b.ticker))]
  const fxPairs = ["GBPEUR=X", "GBPUSD=X"]
  const allNeeded = [...new Set([...posTickers, ...betTickers]), ...fxPairs]
  const prices = await fetchPrices(allNeeded)

  const gbpeur = prices.get("GBPEUR=X")?.price ?? 1.18
  const gbpUSD = prices.get("GBPUSD=X")?.price ?? 1.27
  const gbpPerEur = 1 / gbpeur
  const gbpPerUsd = 1 / gbpUSD

  // ── Positions with live values ───────────────────────────────────────────
  const positionsWithValue: PositionWithValue[] = dbPositions.map((p) => {
    const pd = prices.get(p.ticker)
    let currentPriceGbp: number | null = null
    if (pd?.price != null) {
      if (pd.currency === "EUR") currentPriceGbp = pd.price * gbpPerEur
      else if (pd.currency === "USD") currentPriceGbp = pd.price * gbpPerUsd
      else currentPriceGbp = pd.price
    }

    let costValueGbp = p.avg_cost * p.quantity
    if (p.exchange === "US") costValueGbp = (p.avg_cost * p.quantity) / gbpUSD
    else if (p.exchange === "XETRA" || p.exchange === "EUR")
      costValueGbp = (p.avg_cost * p.quantity) / gbpeur

    const currentValueGbp = currentPriceGbp != null ? currentPriceGbp * p.quantity : null
    const pnlGbp = currentValueGbp != null ? currentValueGbp - costValueGbp : null
    const pnlPct = costValueGbp > 0 && pnlGbp != null ? (pnlGbp / costValueGbp) * 100 : null

    const account = p.account_id ? accountsById.get(p.account_id) : null

    return {
      ...p,
      current_price_gbp: currentPriceGbp != null ? Math.round(currentPriceGbp * 100) / 100 : null,
      current_value_gbp: currentValueGbp != null ? Math.round(currentValueGbp * 100) / 100 : null,
      cost_value_gbp: Math.round(costValueGbp * 100) / 100,
      pnl_gbp: pnlGbp != null ? Math.round(pnlGbp * 100) / 100 : null,
      pnl_pct: pnlPct != null ? Math.round(pnlPct * 100) / 100 : null,
      currency: pd?.currency ?? "GBP",
      account_type: account?.account_type,
    }
  })

  // ── Spread bets with live P&L ────────────────────────────────────────────
  const spreadBetsWithPnl: SpreadBetWithPnl[] = dbBets.map((b) => {
    const pd = prices.get(b.ticker)
    let currentPriceGbp: number | null = null
    if (pd?.price != null) {
      if (pd.currency === "EUR") currentPriceGbp = pd.price * gbpPerEur
      else if (pd.currency === "USD") currentPriceGbp = pd.price / gbpUSD
      else currentPriceGbp = pd.price
    }

    const entryPriceGbp = b.entry_price / gbpUSD
    const notionalGbp = entryPriceGbp * b.stake_per_point

    let pnlGbp: number | null = null
    if (currentPriceGbp != null) {
      const priceDeltaGbp = currentPriceGbp - entryPriceGbp
      pnlGbp =
        b.direction === "long"
          ? priceDeltaGbp * b.stake_per_point
          : -priceDeltaGbp * b.stake_per_point
    }

    return {
      ...b,
      current_price_gbp: currentPriceGbp != null ? Math.round(currentPriceGbp * 100) / 100 : null,
      current_value_gbp: currentPriceGbp != null ? Math.round(currentPriceGbp * 100) / 100 : null,
      pnl_gbp: pnlGbp != null ? Math.round(pnlGbp * 100) / 100 : null,
      pnl_pct:
        notionalGbp > 0 && pnlGbp != null
          ? Math.round((pnlGbp / notionalGbp) * 100 * 100) / 100
          : null,
      notional_gbp: Math.round(notionalGbp * 100) / 100,
    }
  })

  // ── Cash by platform (hledger) ───────────────────────────────────────────
  const cashByPlatform: Map<string, CashBalance[]> = new Map()
  for (const c of hlCash) {
    const list = cashByPlatform.get(c.platform) ?? []
    let amountGbp = c.amount
    if (c.currency === "EUR") amountGbp = c.amount * gbpPerEur
    else if (c.currency === "USD") amountGbp = c.amount * gbpPerUsd
    list.push({
      platform: c.platform,
      currency: c.currency,
      amount: c.amount,
      amount_gbp: amountGbp,
    })
    cashByPlatform.set(c.platform, list)
  }

  // ── Account-level aggregation ──────────────────────────────────────────────
  const accountValues = new Map<
    string,
    {
      account: DbAccount
      cash_gbp: number
      deployed_gbp: number
      spreadbet_gbp: number
      positions: PositionWithValue[]
      bets: SpreadBetWithPnl[]
    }
  >()

  for (const acc of accounts) {
    accountValues.set(acc.id, {
      account: acc,
      cash_gbp: acc.balance,
      deployed_gbp: 0,
      spreadbet_gbp: 0,
      positions: [],
      bets: [],
    })
  }

  // Merge hledger cash into accounts
  const platformToAccountId: Record<string, string> = {
    degiero: "ig-isa",
    "ig-shares": "ig-shares",
    ibkr: "ig-shares",
    pension: "aviva",
    savings: "cash-other",
    test: "ig-isa",
  }

  for (const c of hlCash) {
    const accountId = platformToAccountId[c.platform] ?? c.platform
    const av = accountValues.get(accountId)
    if (!av) continue

    let amountGbp = c.amount
    if (c.currency === "EUR") amountGbp = c.amount * gbpPerEur
    else if (c.currency === "USD") amountGbp = c.amount * gbpPerUsd

    av.cash_gbp += amountGbp
  }

  // Assign positions to accounts
  for (const p of positionsWithValue) {
    const accountId = p.account_id ?? platformToAccountId[p.platform] ?? "ig-shares"
    const av = accountValues.get(accountId)
    if (av) {
      av.deployed_gbp += p.current_value_gbp ?? p.cost_value_gbp
      av.positions.push(p)
    }
  }

  // Assign spread bets to accounts
  for (const b of spreadBetsWithPnl) {
    const av = accountValues.get(b.account_id)
    if (av) {
      av.spreadbet_gbp += b.notional_gbp
      av.bets.push(b)
    }
  }

  // ── Portfolio totals ─────────────────────────────────────────────────────
  let totalCashGbp = 0
  let totalDeployedGbp = 0
  let totalSpreadBetGbp = 0
  for (const av of accountValues.values()) {
    totalCashGbp += av.cash_gbp
    totalDeployedGbp += av.deployed_gbp
    totalSpreadBetGbp += av.spreadbet_gbp
  }

  const cashGbp = totalCashGbp
  const absPortfolioGbp = Math.abs(totalDeployedGbp + totalSpreadBetGbp + cashGbp)
  const totalPortfolioGbp = totalDeployedGbp + totalSpreadBetGbp + cashGbp

  const cashPct = Math.max(0, absPortfolioGbp > 0 ? (cashGbp / absPortfolioGbp) * 100 : 0)
  const deployedPct = Math.max(
    0,
    absPortfolioGbp > 0 ? (totalDeployedGbp / absPortfolioGbp) * 100 : 0,
  )
  const spreadBetPct = Math.max(
    0,
    absPortfolioGbp > 0 ? (totalSpreadBetGbp / absPortfolioGbp) * 100 : 0,
  )

  // ── Allocation bar ───────────────────────────────────────────────────────
  const allocationBar: AllocationBar = {
    targets: {
      cash_reserve_pct: ALLOCATION_TARGETS.cash_reserve_pct,
      spreadbet_pct: ALLOCATION_TARGETS.spreadbet_pct,
      deployed_pct: ALLOCATION_TARGETS.deployed_pct,
    },
    actual: {
      cash_pct: Math.round(cashPct * 100) / 100,
      spreadbet_pct: Math.round(spreadBetPct * 100) / 100,
      deployed_pct: Math.round(deployedPct * 100) / 100,
    },
    buckets: [
      {
        bucket: "cash",
        label: "Cash",
        value_gbp: Math.round(Math.abs(cashGbp) * 100) / 100,
        actual_pct: Math.round(cashPct * 100) / 100,
        target_pct: ALLOCATION_TARGETS.cash_reserve_pct,
        color: "#3b82f6",
      },
      {
        bucket: "deployed",
        label: "Deployed",
        value_gbp: Math.round(totalDeployedGbp * 100) / 100,
        actual_pct: Math.round(deployedPct * 100) / 100,
        target_pct: ALLOCATION_TARGETS.deployed_pct,
        color: "#22c55e",
      },
      {
        bucket: "spreadbet",
        label: "Spread Bet",
        value_gbp: Math.round(totalSpreadBetGbp * 100) / 100,
        actual_pct: Math.round(spreadBetPct * 100) / 100,
        target_pct: ALLOCATION_TARGETS.spreadbet_pct,
        color: "#eab308",
      },
    ],
  }

  // ── Cash breakdown ─────────────────────────────────────────────────────────
  const cashReserveTarget = (ALLOCATION_TARGETS.cash_reserve_pct / 100) * absPortfolioGbp
  const spreadBetTarget = (ALLOCATION_TARGETS.spreadbet_pct / 100) * absPortfolioGbp
  const investableCash = Math.max(0, cashGbp - cashReserveTarget)

  const cashBreakdown: CashBreakdown = {
    total_cash_gbp: Math.round(Math.abs(cashGbp) * 100) / 100,
    cash_negative: cashGbp < 0,
    reserve_gbp: Math.round(cashReserveTarget * 100) / 100,
    reserve_pct: ALLOCATION_TARGETS.cash_reserve_pct,
    spreadbet_allocation_gbp: Math.round(spreadBetTarget * 100) / 100,
    spreadbet_allocation_pct: ALLOCATION_TARGETS.spreadbet_pct,
    investable_gbp: Math.round(investableCash * 100) / 100,
    investable_pct:
      absPortfolioGbp > 0 ? Math.round((investableCash / absPortfolioGbp) * 100 * 100) / 100 : 0,
  }

  // ── Platform allocation (backward compat) ────────────────────────────────
  const positionsByPlatform = new Map<string, PositionWithValue[]>()
  for (const p of positionsWithValue) {
    const list = positionsByPlatform.get(p.platform) ?? []
    list.push(p)
    positionsByPlatform.set(p.platform, list)
  }

  const cashByPlatformGbp = new Map<string, number>()
  for (const [platform, balances] of cashByPlatform) {
    cashByPlatformGbp.set(
      platform,
      balances.reduce((s, c) => s + c.amount_gbp, 0),
    )
  }

  const allPlatforms = [...new Set([...positionsByPlatform.keys(), ...cashByPlatformGbp.keys()])]

  const platformAllocations = allPlatforms.map((platform) => {
    const pos = positionsByPlatform.get(platform) ?? []
    const cashGbpPlat = cashByPlatformGbp.get(platform) ?? 0
    const posValueGbp = pos.reduce((s, p) => s + (p.current_value_gbp ?? p.cost_value_gbp), 0)
    const totalGbp = posValueGbp + cashGbpPlat
    return {
      platform,
      positions: pos,
      cash_gbp: Math.round(cashGbpPlat * 100) / 100,
      position_value_gbp: Math.round(posValueGbp * 100) / 100,
      total_value_gbp: Math.round(totalGbp * 100) / 100,
      weight_pct: absPortfolioGbp > 0 ? Math.round((totalGbp / absPortfolioGbp) * 10000) / 100 : 0,
      cash_pct: totalGbp > 0 ? Math.round((cashGbpPlat / totalGbp) * 10000) / 100 : 0,
    }
  })

  // ── Asset class allocation ───────────────────────────────────────────────
  const etfValueGbp = positionsWithValue
    .filter((p) => classifyTicker(p.ticker, p.exchange) === "etf")
    .reduce((s, p) => s + (p.current_value_gbp ?? p.cost_value_gbp), 0)
  const equityValueGbp = positionsWithValue
    .filter((p) => classifyTicker(p.ticker, p.exchange) === "equity")
    .reduce((s, p) => s + (p.current_value_gbp ?? p.cost_value_gbp), 0)
  const cryptoValueGbp = positionsWithValue
    .filter((p) => classifyTicker(p.ticker, p.exchange) === "crypto")
    .reduce((s, p) => s + (p.current_value_gbp ?? p.cost_value_gbp), 0)

  const assetClassAllocation: AssetClassAllocation[] = [
    {
      assetClass: "cash",
      value_gbp: Math.round(Math.abs(cashGbp) * 100) / 100,
      weight_pct: Math.abs(cashPct),
    },
    {
      assetClass: "equity",
      value_gbp: Math.round(equityValueGbp * 100) / 100,
      weight_pct:
        absPortfolioGbp > 0 ? Math.round((equityValueGbp / absPortfolioGbp) * 10000) / 100 : 0,
    },
    {
      assetClass: "etf",
      value_gbp: Math.round(etfValueGbp * 100) / 100,
      weight_pct:
        absPortfolioGbp > 0 ? Math.round((etfValueGbp / absPortfolioGbp) * 10000) / 100 : 0,
    },
    {
      assetClass: "crypto",
      value_gbp: Math.round(cryptoValueGbp * 100) / 100,
      weight_pct:
        absPortfolioGbp > 0 ? Math.round((cryptoValueGbp / absPortfolioGbp) * 10000) / 100 : 0,
    },
  ].filter((a) => a.value_gbp > 0)

  // ── Accounts summary ───────────────────────────────────────────────────────
  const accountsSummary: AccountSummary[] = [...accountValues.values()].map((av) => ({
    id: av.account.id,
    provider: av.account.provider,
    account_type: av.account.account_type,
    name: av.account.name,
    balance_gbp: Math.round(av.cash_gbp * 100) / 100,
    deployed_gbp: Math.round(av.deployed_gbp * 100) / 100,
    spreadbet_gbp: Math.round(av.spreadbet_gbp * 100) / 100,
    total_value_gbp: Math.round((av.cash_gbp + av.deployed_gbp + av.spreadbet_gbp) * 100) / 100,
    positions_count: av.positions.length,
    bets_count: av.bets.length,
    notes: av.account.notes,
  }))

  // ── Governance ─────────────────────────────────────────────────────────────
  const rules = loadRules()
  const overallAllocations = positionsWithValue.map((p) => ({
    ticker: p.ticker,
    value: p.current_value_gbp ?? p.cost_value_gbp,
    weight:
      absPortfolioGbp > 0 ? ((p.current_value_gbp ?? p.cost_value_gbp) / absPortfolioGbp) * 100 : 0,
  }))
  const overallViolations = checkRules(
    overallAllocations,
    cashPct,
    totalPortfolioGbp,
    totalPortfolioGbp,
    rules,
  )
  const overallSuggestions = suggestRebalance(overallAllocations, cashPct, rules)

  return {
    total_value_gbp: Math.round(totalPortfolioGbp * 100) / 100,
    cash_gbp: Math.round(cashGbp * 100) / 100,
    cash_pct: Math.round(cashPct * 100) / 100,
    cash_pct_raw: Math.round(cashPct * 100) / 100,
    cash_negative: cashGbp < 0,
    position_value_gbp: Math.round(totalDeployedGbp * 100) / 100,
    positions_count: positionsWithValue.length,
    fx_rates: {
      GBPEUR: Math.round(gbpeur * 10000) / 10000,
      GBPUSD: Math.round(gbpUSD * 10000) / 10000,
    },
    allocation_bar: allocationBar,
    cash_breakdown: cashBreakdown,
    accounts: accountsSummary.sort((a, b) => b.total_value_gbp - a.total_value_gbp),
    platforms: platformAllocations.sort((a, b) => b.total_value_gbp - a.total_value_gbp),
    asset_classes: assetClassAllocation,
    spreadbets: spreadBetsWithPnl,
    research_queue: researchQueue,
    governance: { violations: overallViolations, suggestions: overallSuggestions },
  }
}
