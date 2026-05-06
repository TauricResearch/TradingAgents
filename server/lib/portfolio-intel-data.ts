/** Portfolio intelligence data layer — barrel module.
 *
 * Re-exports from sub-modules for backward compatibility.
 * New code should import directly from intel-types.ts, intel-prices.ts,
 * or intel-compute.ts as appropriate.
 */

export { classifyTicker, computePortfolioIntelligence } from "./intel-compute.ts"
export { fetchPrices } from "./intel-prices.ts"
export {
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
  type PlatformAllocation,
  type PortfolioIntel,
  type PositionWithValue,
  type SpreadBetWithPnl,
} from "./intel-types.ts"
