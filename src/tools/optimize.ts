// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** Long-only portfolio weights from price series' history, for analysis, from price_history results referenced whole. */
import { z } from "zod";
import { type Optimization, optimizeOf, type Point } from "../compute/optimize.js";
import { PORTFOLIO } from "../contracts/limits.js";
import { referenceTo } from "./references.js";
import { basisNotes, labelOf, oneCurrency, prepare, RISK_FREE, SERIES } from "./series.js";
import { defineTool, ToolRefusalError } from "./tool.js";

const METHODS = {
  min_variance: "minimum variance",
  max_sharpe: "maximum Sharpe ratio",
  risk_parity: "risk parity (equal risk contributions)",
} as const;

/** A weight as a result shows it: four decimals (the record keeps it unrounded). */
const weight = (value: number) => Number(value.toFixed(4));

export function optimizePortfolioTool() {
  return defineTool({
    name: "optimize_portfolio",
    description:
      `Long-only weights for 2 to ${PORTFOLIO.holdings} holdings in one currency from their daily history, each a price_history result referenced whole (${referenceTo("e7")}) ` +
      "or given: min_variance (the least volatile mix), max_sharpe (the highest excess return per unit of volatility) or " +
      "risk_parity (each holding contributing the same risk), with an optional cap per holding, and points on the efficient " +
      "frontier for the mean-variance methods. max_sharpe needs weights whose expected return beats the risk-free rate. " +
      "The covariance is Ledoit-Wolf shrunk. Expected returns are the window's mean daily returns, which are noisy, so " +
      "max_sharpe and the frontier depend on estimates that may not repeat; min_variance and risk_parity need no return " +
      "estimate. This is analysis of past data, not advice: the weights show what the window's estimates imply, and " +
      "portfolio_risk measures any weights on the history.",
    kind: "compute",
    parallelSafe: true,
    input: z.object({
      series: z.array(SERIES).min(2).max(PORTFOLIO.holdings),
      method: z.enum(["min_variance", "max_sharpe", "risk_parity"]),
      max_weight: z
        .number()
        .gt(0)
        .max(1)
        .optional()
        .describe("The largest weight one holding may take, such as 0.25; no cap by default"),
      risk_free_annual_pct: RISK_FREE,
      frontier_points: z
        .number()
        .int()
        .min(0)
        .max(PORTFOLIO.frontierPoints)
        .default(5)
        .describe(
          "Points on the efficient frontier from least volatility to the highest return, its ends included " +
            "(min_variance and max_sharpe); 1 for the least-volatile point alone, 0 for none",
        ),
    }),
    output: z.object({
      risk_free_annual_pct: z.number(),
      optimization: z.custom<Optimization>((v) => !!v && typeof v === "object" && "portfolio" in v),
    }),
    label: ({ series, method }) => `${series.map((one) => labelOf(one)).join(", ")} (${method})`,
    async run({ series, method, max_weight, risk_free_annual_pct, frontier_points }, { signal }) {
      const prepared = series.map((one) => prepare(one));
      const currencies = oneCurrency("optimize_portfolio", prepared);
      const result = await optimizeOf(prepared, {
        method,
        ...(max_weight === undefined ? {} : { maxWeight: max_weight }),
        riskFreePct: risk_free_annual_pct,
        frontierPoints: frontier_points,
        signal,
      });
      if ("error" in result) throw new ToolRefusalError(`optimize_portfolio: ${result.error}`);
      const optimization = {
        ...result,
        notes: [
          ...prepared.flatMap((one) => one.notes),
          ...currencies,
          ...basisNotes(prepared),
          ...result.notes,
        ],
      };
      return {
        payload: { risk_free_annual_pct, optimization },
        provenance: { source: "computed", syncs: true, as_of: result.to },
        summary: `${method}: ${result.portfolio.weights.map((w) => `${w.label} ${weight(w.weight)}`).join(", ")}`,
      };
    },
    render({ risk_free_annual_pct, optimization: o }) {
      const figures = (point: Point) =>
        `return ${point.return_pct}% a year, volatility ${point.volatility_pct}%, Sharpe ${point.sharpe ?? "not defined"}`;
      return [
        `${METHODS[o.method]}: ${o.from} to ${o.to}, ${o.returns} daily returns on the dates every holding shares; long-only, weights sum to 1${o.max_weight === null || o.method === "risk_parity" ? "" : `, at most ${o.max_weight} each`}`,
        `- estimates: Ledoit-Wolf shrunk covariance of daily returns (shrinkage ${o.shrinkage}); expected returns the mean daily returns; annualized by ${o.sessions_per_year} sessions`,
        `- weights (share of the portfolio's variance): ${o.portfolio.weights.map((w) => `${w.label} ${weight(w.weight)} (${w.risk_share_pct === null ? "not defined" : `${w.risk_share_pct}%`})`).join("; ")}`,
        `- in-sample, under these estimates: ${figures(o.portfolio)} (risk-free ${risk_free_annual_pct}%)`,
        ...(o.frontier.length
          ? [
              "- efficient frontier, least volatility at each return (weights in the order above):",
              ...o.frontier.map(
                (point, i) =>
                  `  ${i + 1}. ${figures(point)}: ${point.weights.map((w) => `${w.label} ${weight(w.weight)}`).join(", ")}`,
              ),
            ]
          : []),
        ...o.notes.map((note) => `- note: ${note}`),
        "- these weights describe what the window's estimates imply: analysis of past data, not advice",
      ];
    },
  });
}
