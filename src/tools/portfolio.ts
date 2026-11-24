// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** Risk of a portfolio of price series at given weights, from price_history results referenced whole. */
import { z } from "zod";
import { type PortfolioRisk, portfolioRiskOf } from "../compute/portfolio.js";
import { PORTFOLIO } from "../contracts/limits.js";
import { referenceTo } from "./references.js";
import { relativeLines, riskLines } from "./risk.js";
import { basisNotes, labelOf, oneCurrency, prepare, RISK_FREE, SERIES } from "./series.js";
import { defineTool, ToolRefusalError } from "./tool.js";

export function portfolioRiskTool() {
  return defineTool({
    name: "portfolio_risk",
    description:
      `Risk of a long-only portfolio of 2 to ${PORTFOLIO.holdings} holdings in one currency, each a price_history result referenced whole (${referenceTo("e7")}) ` +
      "or given, with its weight (weights are scaled to sum to 1), held at constant weights rebalanced daily: returns over " +
      "1 week to 1 year, annualized return and volatility, the deepest drawdown, 1-day VaR and expected shortfall, Sharpe, " +
      "Sortino and Calmar, the correlation matrix, each holding's share of the portfolio's variance, the effective number " +
      "of holdings by weight and by risk, and beta against a benchmark when one is given.",
    kind: "compute",
    parallelSafe: true,
    input: z.object({
      holdings: z
        .array(
          z.object({
            series: SERIES,
            weight: z
              .number()
              .describe("The holding's weight, such as 0.25 or 25; weights are scaled to sum to 1"),
          }),
        )
        .min(2)
        .max(PORTFOLIO.holdings),
      benchmark: SERIES.optional().describe(
        `A benchmark's price_history result (such as SPY's), ${referenceTo("e7")}`,
      ),
      risk_free_annual_pct: RISK_FREE,
    }),
    output: z.object({
      risk_free_annual_pct: z.number(),
      portfolio: z.custom<PortfolioRisk>((v) => !!v && typeof v === "object" && "holdings" in v),
    }),
    label: ({ holdings, benchmark }) =>
      `${holdings.map((one) => `${labelOf(one.series)} ${one.weight}`).join(", ")}${benchmark ? ` vs ${labelOf(benchmark)}` : ""}`,
    async run({ holdings, benchmark, risk_free_annual_pct }) {
      const prepared = holdings.map((one) => ({ series: prepare(one.series), weight: one.weight }));
      const currencies = oneCurrency(
        "portfolio_risk",
        prepared.map((one) => one.series),
      );
      const base = benchmark === undefined ? undefined : prepare(benchmark);
      const held = prepared.find((one) => one.series.currency)?.series.currency;
      if (base?.currency && held && base.currency !== held) {
        currencies.push(
          `the benchmark ${base.label} is quoted in ${base.currency} and the holdings in ${held}, so beta compares returns in different currencies`,
        );
      }
      const result = portfolioRiskOf(prepared, {
        ...(base ? { benchmark: base } : {}),
        riskFreePct: risk_free_annual_pct,
      });
      if ("error" in result) throw new ToolRefusalError(`portfolio_risk: ${result.error}`);
      const sources = [...prepared.map((one) => one.series), ...(base ? [base] : [])];
      const portfolio = {
        ...result,
        notes: [
          ...sources.flatMap((one) => one.notes),
          ...currencies,
          ...basisNotes(sources),
          ...result.notes,
        ],
      };
      return {
        payload: { risk_free_annual_pct, portfolio },
        provenance: { source: "computed", syncs: true, as_of: result.risk.to },
        summary: `vol ${result.risk.volatility_pct ?? "n/a"}%, max drawdown ${result.risk.max_drawdown?.depth_pct ?? 0}%, effective holdings ${result.effective_holdings.by_weight} by weight and ${result.effective_holdings.by_risk ?? "n/a"} by risk`,
      };
    },
    render({ risk_free_annual_pct, portfolio }) {
      const { risk, correlation, effective_holdings: effective } = portfolio;
      return [
        `portfolio: ${risk.from} to ${risk.to}, ${risk.returns} daily returns on the dates every holding shares; constant weights, rebalanced daily; value ${risk.last_close.toFixed(2)} from 100 at the start`,
        `- holdings (weight; share of the portfolio's variance, w_i (Sigma w)_i / w' Sigma w from the sample covariance of daily returns): ${portfolio.holdings.map((h) => `${h.label} ${h.weight} (${h.variance_share_pct === null ? "not defined" : `${h.variance_share_pct}%`})`).join("; ")}`,
        `- effective number of holdings (1 / sum of squares): ${effective.by_weight} by weight, ${effective.by_risk ?? "not defined"} by share of variance`,
        ...riskLines(
          { ...risk, notes: [], sessions_per_year: portfolio.sessions_per_year },
          risk_free_annual_pct,
        ).slice(1),
        `- correlation of daily returns (rows and columns ${correlation.labels.join(", ")}):`,
        ...correlation.matrix.map(
          (row, i) =>
            `  ${correlation.labels[i]}: ${row.map((value) => (value === null ? "n/a" : value)).join(", ")}`,
        ),
        ...(portfolio.benchmark
          ? relativeLines({ ...portfolio.benchmark, notes: [] }, risk_free_annual_pct)
          : []),
        ...[...portfolio.notes, ...risk.notes, ...(portfolio.benchmark?.notes ?? [])].map(
          (note) => `- note: ${note}`,
        ),
      ];
    },
  });
}
