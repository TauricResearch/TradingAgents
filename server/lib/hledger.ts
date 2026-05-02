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

import { spawn } from "node:child_process";

const DEFAULT_JOURNAL = process.env.HLEDGER_FILE ?? `${process.env.HOME}/.hledger.journal`;

interface HLAmount {
  aquantity: { floatingPoint: number };
  acommodity: string;
  acost?: {
    contents: {
      aquantity: { floatingPoint: number };
      acommodity: string;
    };
  };
}

interface HLBalanceRow {
  0: string;   // full account name
  1: string;   // short name
  2: number;   // depth
  3: HLAmount[];
}

export interface HLHolding {
  ticker: string;
  quantity: number;
  costBasis: number;     // total cost in EUR
  costPerShare: number;  // average cost per share
}

export interface HLCashBalance {
  currency: string;
  amount: number;
}

export interface HLResult {
  holdings: HLHolding[];
  cash: HLCashBalance[];
  errors?: string[];
}

function runHledger(args: string[], journal: string = DEFAULT_JOURNAL): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn("hledger", ["-f", journal, ...args], {
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
        reject(new Error(`hledger exited with code ${code}: ${stderr.trim()}`));
        return;
      }
      resolve(stdout);
    });

    child.on("error", reject);
  });
}

/**
 * Parse a hLedger balance --tree -O json output into holdings + cash.
 */
export function parseBalanceJson(raw: string): HLResult {
  const rows = JSON.parse(raw) as [HLBalanceRow[], HLAmount[]];
  const balanceRows = rows[0];
  const holdings: HLHolding[] = [];
  const cash: HLCashBalance[] = [];

  for (const row of balanceRows) {
    // Skip Equity and root accounts
    if (row[0].startsWith("Equity") || row[0] === "" || row[2] === 0) continue;

    for (const amt of row[3]) {
      const qty = amt.aquantity.floatingPoint;
      const commodity = amt.acommodity;

      // Skip zero balances
      if (qty === 0) continue;

      // Cash accounts (EUR, USD, GBP, etc.)
      if (isCurrency(commodity)) {
        cash.push({ currency: commodity, amount: qty });
        continue;
      }

      // Holdings (stocks, ETFs, crypto)
      const costBasis = amt.acost?.contents.aquantity.floatingPoint ?? 0;
      const costPerShare = qty !== 0 ? costBasis / qty : 0;

      holdings.push({
        ticker: commodity.replace(/^"|"$/g, ""), // strip quotes
        quantity: qty,
        costBasis,
        costPerShare,
      });
    }
  }

  return { holdings, cash };
}

function isCurrency(c: string): boolean {
  return ["EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD", "SEK", "NOK", "DKK"].includes(
    c.replace(/^"|"$/g, ""),
  );
}

/**
 * Get current holdings from hLedger.
 */
export async function getHoldings(journal?: string): Promise<HLResult> {
  const raw = await runHledger(["balance", "--tree", "-O", "json"], journal);
  return parseBalanceJson(raw);
}

/**
 * Get price history from hLedger.
 * Returns array of { date, ticker, price, currency }
 */
export async function getPrices(journal?: string): Promise<
  Array<{ date: string; ticker: string; price: number; currency: string }>
> {
  const raw = await runHledger(["prices", "-O", "json"], journal);
  const entries = JSON.parse(raw) as Array<{
    pdate: string;
    pcommodity: string;
    pprice: { aquantity: { floatingPoint: number }; acommodity: string };
  }>;

  return entries.map((e) => ({
    date: e.pdate,
    ticker: e.pcommodity.replace(/^"|"$/g, ""),
    price: e.pprice.aquantity.floatingPoint,
    currency: e.pprice.acommodity,
  }));
}

/**
 * Get allocation tree (market value by account).
 */
export async function getAllocation(journal?: string): Promise<string> {
  return runHledger(["balance", "--tree", "--value", "end", "--depth", "3"], journal);
}
