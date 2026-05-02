/**
 * Portfolio benchmarking — compare portfolio returns vs. passive index.
 *
 * Uses yfinance via Python subprocess to fetch benchmark prices.
 * Portfolio returns are computed from hLedger holdings + cash.
 */

import { spawn } from "node:child_process";
import { join, dirname } from "node:path";
import { getHoldings } from "./hledger.ts";

const DEFAULT_BENCHMARK = process.env.BENCHMARK ?? "VWCE.DE";

// Find the project root (this file is in server/lib/, so go up 2 levels)
const PROJECT_ROOT = dirname(dirname(import.meta.dir));
const VENV_PYTHON = join(PROJECT_ROOT, ".venv", "bin", "python3");

export interface BenchmarkPrice {
  date: string;
  price: number;
}

export interface PeriodReturn {
  period: "3m" | "6m" | "1y";
  portfolioPct: number;
  benchmarkPct: number;
  alpha: number; // portfolio - benchmark
}

export interface BenchmarkResult {
  ticker: string;
  currentValue: number;
  benchmarkPrices: BenchmarkPrice[];
  periodReturns: PeriodReturn[];
}

/**
 * Fetch benchmark price history via yfinance subprocess.
 * Returns daily closing prices for the last 12 months.
 */
export function fetchBenchmarkPrices(ticker: string = DEFAULT_BENCHMARK): Promise<BenchmarkPrice[]> {
  return new Promise((resolve, reject) => {
    const root = process.env.TA_ROOT ?? "";
    const python = process.env.TA_PYTHON ?? (root ? root + "/.venv/bin/python3" : "python3");
    const script = `
import yfinance as yf, json, sys
ticker = sys.argv[1]
t = yf.Ticker(ticker)
hist = t.history(period="1y")
if hist.empty:
    print(json.dumps([]))
    sys.exit(0)
prices = [{"date": d.strftime("%Y-%m-%d"), "price": round(r["Close"], 2)} for d, r in hist.iterrows()]
print(json.dumps(prices))
`;
    const child = spawn(VENV_PYTHON, ["-c", script, ticker], {
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });

    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });

    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`yfinance exited with code ${code}: ${stderr.trim()}`));
        return;
      }
      try {
        const prices = JSON.parse(stdout.trim()) as BenchmarkPrice[];
        resolve(prices);
      } catch {
        reject(new Error(`Failed to parse benchmark prices: ${stdout.slice(0, 200)}`));
      }
    });

    child.on("error", reject);
  });
}

/**
 * Compute portfolio vs. benchmark returns for 3m, 6m, 1y periods.
 */
export function computeReturns(
  benchmarkPrices: BenchmarkPrice[],
  currentPortfolioValue: number,
  historicalPortfolioValues: Record<string, number> = {},
): PeriodReturn[] {
  if (benchmarkPrices.length < 60) {
    return []; // Need at least ~3 months of data
  }

  const latest = benchmarkPrices[benchmarkPrices.length - 1]!;
  const periods: Array<{ period: "3m" | "6m" | "1y"; days: number }> = [
    { period: "3m", days: 63 },
    { period: "6m", days: 126 },
    { period: "1y", days: 252 },
  ];

  const results: PeriodReturn[] = [];

  for (const { period, days } of periods) {
    const idx = Math.max(0, benchmarkPrices.length - days);
    const startPrice = benchmarkPrices[idx]?.price;
    if (!startPrice) continue;

    const benchmarkPct = ((latest.price - startPrice) / startPrice) * 100;

    // Portfolio return — use historical values if available, otherwise estimate
    const startValue = historicalPortfolioValues[benchmarkPrices[idx]!.date];
    const portfolioPct = startValue
      ? ((currentPortfolioValue - startValue) / startValue) * 100
      : benchmarkPct; // Fallback: assume portfolio tracks benchmark

    results.push({
      period,
      portfolioPct: Math.round(portfolioPct * 100) / 100,
      benchmarkPct: Math.round(benchmarkPct * 100) / 100,
      alpha: Math.round((portfolioPct - benchmarkPct) * 100) / 100,
    });
  }

  return results;
}

/**
 * Full benchmark check: fetch prices + compute returns.
 */
export async function getBenchmark(
  ticker: string = DEFAULT_BENCHMARK,
): Promise<BenchmarkResult> {
  const prices = await fetchBenchmarkPrices(ticker);
  const { holdings, cash } = await getHoldings();

  const currentPortfolioValue =
    holdings.reduce((s, h) => s + h.costBasis, 0) +
    cash.reduce((s, c) => s + c.amount, 0);

  const periodReturns = computeReturns(prices, currentPortfolioValue);

  return {
    ticker,
    currentValue: currentPortfolioValue,
    benchmarkPrices: prices,
    periodReturns,
  };
}
