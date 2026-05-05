/** Shared types used across multiple route files. */

export interface PriceResult {
  price: number | null
  currency: string
}

// Re-export from lib/benchmark.ts for use in routes
export type { BenchmarkPrice, PeriodReturn } from "./benchmark.ts"
