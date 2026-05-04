#!/usr/bin/env bun
/**
 * Print portfolio intelligence summary as plain text.
 *
 * Usage:
 *   bun run scripts/portfolio-intel.ts [dev|test]
 *
 * Default: dev (localhost:3000)
 */

const PORT = process.env.TA_DASHBOARD_PORT ?? "3000";
const mode = Bun.argv[2] ?? "dev";

const URL =
  mode === "test"
    ? `http://localhost:${PORT}/api/portfolio/intelligence?mode=test`
    : `http://localhost:${PORT}/api/portfolio/intelligence`;

interface IntelligenceResponse {
  portfolio: {
    total_value_gbp: number;
    cash_gbp: number;
    cash_pct: number;
    positions_count: number;
    position_value_gbp: number;
  };
  asset_classes: Array<{
    assetClass: string;
    weight_pct: number;
    value_gbp: number;
  }>;
  platforms: Array<{
    platform: string;
    weight_pct: number;
    cash_gbp?: number;
  }>;
  governance: {
    violations: Array<{
      detail: string;
      rule: { name: string };
    }>;
  };
}

function fmt(n: number): string {
  return `£${n.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function pct(n: number): string {
  return `${n.toFixed(1)}%`;
}

async function main() {
  let data: IntelligenceResponse;
  try {
    const res = await fetch(URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch (e) {
    console.error(`Failed to fetch ${URL}: ${e}`);
    process.exit(1);
  }

  const pf = data.portfolio;
  console.log(`=== Portfolio Intelligence (${mode.toUpperCase()} GBP) ===`);
  console.log(`  Total:     ${fmt(pf.total_value_gbp)}`);
  console.log(`  Cash:      ${fmt(pf.cash_gbp)}  (${pct(pf.cash_pct)})`);
  console.log(`  Positions: ${pf.positions_count} @ ${fmt(pf.position_value_gbp)}`);
  console.log();

  for (const a of data.asset_classes ?? []) {
    console.log(`  ${a.assetClass.padEnd(10)} ${pct(a.weight_pct).padStart(7)}  ${fmt(a.value_gbp)}`);
  }
  console.log();

  for (const p of data.platforms ?? []) {
    const cash = p.cash_gbp !== undefined ? `  cash: ${fmt(p.cash_gbp)}` : "";
    console.log(`  ${p.platform.padEnd(12)} ${pct(p.weight_pct).padStart(7)}${cash}`);
  }
  console.log();

  const violations = data.governance?.violations ?? [];
  console.log(`  Governance violations: ${violations.length}`);
  for (const v of violations) {
    console.log(`    ! ${v.rule.name}: ${v.detail}`);
  }
}

main();