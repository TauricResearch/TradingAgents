// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * A discounted cash flow valuation and the cost of capital it discounts at. Every assumption is an input;
 * rates are in percent a year (9 is 9%). Flows are discounted at the end of each year from the valuation
 * date, or at mid-year when asked; the terminal value is a perpetuity growing at the terminal rate.
 */
import { round } from "./series.js";

export type Wacc = {
  cost_of_equity_pct: number;
  after_tax_cost_of_debt_pct: number;
  equity_weight: number;
  debt_weight: number;
  wacc_pct: number;
};

type WaccInputs = {
  risk_free_pct: number;
  beta: number;
  equity_risk_premium_pct: number;
  cost_of_debt_pct: number;
  tax_rate_pct: number;
  /** Market values the weights come from. */
  equity_value: number;
  debt_value: number;
};

/** CAPM cost of equity and the weighted cost of capital. */
export function waccOf(inputs: WaccInputs): Wacc | { error: string } {
  const { equity_value: equity, debt_value: debt } = inputs;
  if (!(equity > 0) || debt < 0)
    return { error: "the equity value must be positive and the debt value not negative" };
  const costOfEquity = inputs.risk_free_pct + inputs.beta * inputs.equity_risk_premium_pct;
  const afterTax = inputs.cost_of_debt_pct * (1 - inputs.tax_rate_pct / 100);
  const equityWeight = equity / (equity + debt);
  return {
    cost_of_equity_pct: round(costOfEquity),
    after_tax_cost_of_debt_pct: round(afterTax),
    equity_weight: round(equityWeight, 4),
    debt_weight: round(1 - equityWeight, 4),
    wacc_pct: round(equityWeight * costOfEquity + (1 - equityWeight) * afterTax, 4),
  };
}

type DcfInputs = {
  /** The cash flows of each year ahead, given; or grown from `base` through `stages`. */
  flows?: number[];
  base?: number;
  stages?: { years: number; growth_pct: number }[];
  terminal_growth_pct: number;
  discount_pct: number;
  /** Debt less cash, taken from the enterprise value to reach the equity value. */
  net_debt: number;
  shares?: number;
  market_cap?: number;
  mid_year?: boolean;
  /** The discount rates and terminal growth rates of the sensitivity grid. */
  grid?: { discount_pcts: number[]; growth_pcts: number[] };
};

export type Dcf = {
  flows: { year: number; flow: number; discount_factor: number; present_value: number }[];
  present_value_of_flows: number;
  terminal_value: number;
  present_value_of_terminal: number;
  enterprise_value: number;
  /** The terminal value's share of the enterprise value. */
  terminal_share_pct: number;
  equity_value: number;
  per_share: number | null;
  /** The equity value against the market capitalization. */
  vs_market_cap_pct: number | null;
  grid: { discount_pcts: number[]; growth_pcts: number[]; equity_values: (number | null)[][] } | null;
  notes: string[];
};

/** The terminal value's share of the enterprise value above which the result rests mostly on it. */
const TERMINAL_HEAVY = 75;

export function dcfOf(inputs: DcfInputs): Dcf | { error: string } {
  const flows = projected(inputs);
  if ("error" in flows) return flows;
  const checked = rates(inputs.discount_pct, inputs.terminal_growth_pct);
  if (checked) return { error: checked };
  const core = value(
    flows,
    inputs.discount_pct,
    inputs.terminal_growth_pct,
    inputs.net_debt,
    inputs.mid_year,
  );
  const notes: string[] = [];
  const terminalShare = (core.present_value_of_terminal / core.enterprise_value) * 100;
  if (terminalShare > TERMINAL_HEAVY) {
    notes.push(
      `the terminal value is ${terminalShare.toFixed(0)}% of the enterprise value: the result rests mostly on the terminal growth and discount rates`,
    );
  }
  if (core.equity_value <= 0)
    notes.push("the enterprise value does not cover the net debt: the equity value is not positive");
  const grid = inputs.grid
    ? {
        discount_pcts: inputs.grid.discount_pcts,
        growth_pcts: inputs.grid.growth_pcts,
        equity_values: inputs.grid.discount_pcts.map(
          (r) =>
            inputs.grid?.growth_pcts.map((g) =>
              rates(r, g)
                ? null
                : round(value(flows, r, g, inputs.net_debt, inputs.mid_year).equity_value, 0),
            ) ?? [],
        ),
      }
    : null;
  return {
    flows: core.flows,
    present_value_of_flows: round(core.present_value_of_flows, 0),
    terminal_value: round(core.terminal_value, 0),
    present_value_of_terminal: round(core.present_value_of_terminal, 0),
    enterprise_value: round(core.enterprise_value, 0),
    terminal_share_pct: round(terminalShare, 1),
    equity_value: round(core.equity_value, 0),
    per_share: inputs.shares && inputs.shares > 0 ? round(core.equity_value / inputs.shares) : null,
    vs_market_cap_pct:
      inputs.market_cap && inputs.market_cap > 0
        ? round((core.equity_value / inputs.market_cap - 1) * 100, 1)
        : null,
    grid,
    notes,
  };
}

/** Why a discount and terminal growth rate pair cannot be used, or nothing when it can. */
function rates(discount: number, growth: number): string | undefined {
  if (discount < 1) return `a discount rate of ${discount}% is below 1%: rates are in percent (9 is 9%)`;
  if (growth >= discount)
    return `the terminal growth rate (${growth}%) must be below the discount rate (${discount}%)`;
  return undefined;
}

function projected(inputs: DcfInputs): number[] | { error: string } {
  if (inputs.flows?.length) return inputs.flows;
  const { base, stages } = inputs;
  if (base === undefined || !stages?.length)
    return { error: "give the flows, or a base flow and growth stages" };
  if (base <= 0)
    return { error: "a base flow at or below zero cannot be grown; give the flows of each year instead" };
  const out: number[] = [];
  let flow = base;
  for (const stage of stages) {
    for (let year = 0; year < stage.years; year++) {
      flow *= 1 + stage.growth_pct / 100;
      out.push(flow);
    }
  }
  return out;
}

function value(flows: number[], discount: number, growth: number, netDebt: number, midYear = false) {
  const r = discount / 100;
  const g = growth / 100;
  const discounted = flows.map((flow, i) => {
    const factor = 1 / (1 + r) ** (i + 1 - (midYear ? 0.5 : 0));
    return {
      year: i + 1,
      flow: round(flow, 0),
      discount_factor: round(factor, 6),
      present_value: round(flow * factor, 0),
      exact: flow * factor,
    };
  });
  const presentFlows = discounted.reduce((sum, row) => sum + row.exact, 0);
  const last = flows.at(-1) as number;
  const terminal = (last * (1 + g)) / (r - g);
  // The terminal value is reached at the end of the last year.
  const presentTerminal = terminal / (1 + r) ** flows.length;
  const enterprise = presentFlows + presentTerminal;
  return {
    flows: discounted.map(({ exact: _, ...row }) => row),
    present_value_of_flows: presentFlows,
    terminal_value: terminal,
    present_value_of_terminal: presentTerminal,
    enterprise_value: enterprise,
    equity_value: enterprise - netDebt,
  };
}
