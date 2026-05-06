/** @jsxImportSource hono/jsx */

import type { PortfolioIntel } from "../lib/portfolio-intel-data.ts"
import { AccountsTable } from "./partials/intel-accounts.tsx"
import { AllocationBarSection } from "./partials/intel-allocation.tsx"
import { AssetClassBars } from "./partials/intel-asset-class.tsx"
import { CashBreakdownPanel } from "./partials/intel-cash.tsx"
import { GovernancePanel } from "./partials/intel-governance.tsx"
import { IntelHero } from "./partials/intel-hero.tsx"
import { PlatformTable } from "./partials/intel-platforms.tsx"
import { ResearchQueue } from "./partials/intel-research.tsx"
import { SpreadBetTable } from "./partials/intel-spreadbets.tsx"

export function PortfolioIntelView({ data }: { data: PortfolioIntel }) {
  return (
    <>
      <IntelHero data={data} />
      <AllocationBarSection bar={data.allocation_bar} />
      <CashBreakdownPanel breakdown={data.cash_breakdown} />
      <AccountsTable accounts={data.accounts} />
      <SpreadBetTable bets={data.spreadbets} />
      <ResearchQueue items={data.research_queue} />
      <AssetClassBars assetClasses={data.asset_classes} totalValue={data.total_value_gbp} />
      <PlatformTable platforms={data.platforms} />
      <GovernancePanel data={data} />
    </>
  )
}
