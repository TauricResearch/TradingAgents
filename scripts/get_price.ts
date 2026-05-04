#!/usr/bin/env bun
/**
 * Fetch current price and recent history for a ticker via Yahoo Finance API.
 *
 * Usage:
 *   bun run scripts/get_price.ts TICKER
 *
 * Outputs JSON to stdout:
 *   {
 *     "ticker": "AAPL",
 *     "price": 192.50,
 *     "currency": "USD",
 *     "previousClose": 191.00,
 *     "dayHigh": 193.20,
 *     "dayLow": 191.50,
 *     "volume": 45000000,
 *     "history": [{"date": "2026-05-01", "close": 191.00}, ...]
 *   }
 */

const TICKER = Bun.argv[2];

if (!TICKER) {
  console.error("Usage: get_price.ts TICKER");
  process.exit(1);
}

interface Meta {
  regularMarketPrice: number | null;
  currency: string;
  previousClose: number | null;
  regularMarketDayHigh: number | null;
  regularMarketDayLow: number | null;
  regularMarketVolume: number | null;
}

interface Quote {
  Date: string;
  Close: number;
}

interface YFChartResponse {
  chart: {
    result: Array<{
      meta: Meta;
      timestamp: number[];
      indicators: {
        quote: Array<{ quote: Quote[] }>;
        adjclose: Array<{ adjclose: number[] }>;
      };
    }> | null;
    error: { code: string; description: string } | null;
  };
}

async function getPrice(ticker: string): Promise<object> {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?interval=1d&range=1mo`;

  const res = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0",
      Accept: "application/json",
    },
  });

  if (!res.ok) {
    throw new Error(`HTTP ${res.status} for ${ticker}`);
  }

  const data: YFChartResponse = await res.json();

  if (data.chart.error) {
    throw new Error(`${data.chart.error.code}: ${data.chart.error.description}`);
  }

  const result = data.chart.result?.[0];
  if (!result) throw new Error(`No data for ${ticker}`);

  const { meta, timestamp, indicators } = result;
  // quote is [{ quote: [...] }] — use adjclose for adjusted close prices
  const adjcloseArr = indicators.adjclose?.[0]?.adjclose ?? [];

  const history = (timestamp ?? [])
    .map((ts, i) => ({
      date: new Date(ts * 1000).toISOString().split("T")[0],
      close: adjcloseArr[i] != null ? Math.round(adjcloseArr[i] * 100) / 100 : null,
    }))
    .filter((h) => h.close !== null);

  return {
    ticker,
    price: meta.regularMarketPrice ?? null,
    currency: meta.currency ?? "USD",
    previousClose: meta.previousClose ?? null,
    dayHigh: meta.regularMarketDayHigh ?? null,
    dayLow: meta.regularMarketDayLow ?? null,
    volume: meta.regularMarketVolume ?? 0,
    history,
  };
}

getPrice(TICKER)
  .then((data) => console.log(JSON.stringify(data, null, 2)))
  .catch((e) => {
    console.error(`Error fetching ${TICKER}: ${e.message}`);
    process.exit(1);
  });