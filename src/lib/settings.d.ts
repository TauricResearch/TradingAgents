/**
 * Module declarations for src/lib/ TypeScript files.
 * Required because tsconfig.server.json uses moduleResolution: bundler
 * which does not resolve relative ../.. paths to src/lib/ in TS 6.x.
 */
declare module "@lib/settings" {
  export const cfg: {
    isTestMode: boolean
    paths: {
      resultsDir: string
      positionsDir: string
      postMortemsDir: string
      decisionsDir: string
      hledgerJournal: string
      testHledgerJournal: string
      memoryLog: string
      cacheDir: string
    }
    hledger: { journal: string; testJournal: string }
    portfolio: { db: string }
    app: {
      benchmarkTicker: string
      dashboardPort: number
      openRouterApiKey: string
      hasOpenRouter: boolean
    }
    trading: {
      defaultPlatform: string
      defaultMode: string
      defaultAccountBalance: number
      defaultRiskPerTrade: number
    }
    timeouts: { analysisIdleSeconds: number }
  }
  export type Config = typeof cfg
}

declare module "@lib/types" {
  export interface PriceResult {
    price: number | null
    currency: string
  }
  export type { BenchmarkPrice, PeriodReturn } from "src/server/lib/benchmark"
}

declare module "@lib/db" {
  import type { Database } from "bun:sqlite"

  export { Database }
  export const DatabaseFactory: {
    connect(path: string): Database
    get(): Database
    close(): void
    isConnected(): boolean
    path: string | null
  }
}
