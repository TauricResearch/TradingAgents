// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Return and risk figures of price series, and beta against a benchmark, from price_history results
 * referenced whole ({"ref": "e7"}) or series given directly.
 */
import { z } from "zod";
import { type Relative, type Risk, relativeOf, riskOf } from "../compute/risk.js";
import { hint } from "./preview.js";
import { referenceTo } from "./references.js";
import { basisNotes, labelOf, prepare, RISK_FREE, SERIES } from "./series.js";
import { defineTool, ToolRefusalError } from "./tool.js";

const FAILED = z.object({ label: z.string(), error: z.string() });

/** The figures of each series, or why one has none. */
const RISKS = z.object({
  risk_free_annual_pct: z.number(),
  /** What the sources say about the series together: the price basis they share, or each one's. */
  notes: z.array(z.string()),
  results: z.array(
    z.union([
      z.custom<Risk & { sessions_per_year: number }>((v) => !!v && typeof v === "object" && "returns" in v),
      FAILED,
    ]),
  ),
});

export function returnsRiskTool() {
  return defineTool({
    name: "returns_risk",
    description:
      `Returns and risk of 1 to 10 price series, each a price_history result referenced whole (${referenceTo("e7")}) or given: ` +
      "returns over 1 week to 1 year, annualized return and volatility, the deepest drawdown and its recovery, " +
      "1-day historical VaR and expected shortfall at 95%, best and worst day, Sharpe and Sortino against a risk-free rate, " +
      "and Calmar (annualized return over the deepest drawdown). " +
      "Several series are compared side by side.",
    kind: "compute",
    parallelSafe: true,
    input: z.object({ series: z.array(SERIES).min(1).max(10), risk_free_annual_pct: RISK_FREE }),
    output: RISKS,
    // One row a series: its return, volatility, deepest drawdown and Sharpe ratio.
    preview: [
      hint(RISKS, {
        list: "results",
        fields: [
          "label",
          { field: "total_return_pct", as: "signed" },
          { field: "volatility_pct", label: "vol", as: "percent" },
          { field: "max_drawdown.depth_pct", label: "max drawdown", as: "percent" },
          { field: "sharpe", label: "Sharpe" },
        ],
        except: "error",
        replacesSummary: true,
      }),
    ],
    label: ({ series }) => series.map((one) => labelOf(one)).join(", "),
    async run({ series, risk_free_annual_pct }) {
      const sources = series.map((one) => prepare(one));
      const results = sources.map((prepared) => {
        const risk = riskOf(prepared, risk_free_annual_pct);
        return "error" in risk
          ? { label: prepared.label, error: risk.error }
          : { ...risk, sessions_per_year: prepared.perYear, notes: [...prepared.notes, ...risk.notes] };
      });
      const to = latestComputed(results);
      return {
        payload: { risk_free_annual_pct, notes: basisNotes(sources), results },
        provenance: { source: "computed", syncs: true, ...(to ? { as_of: to } : {}) },
        summary: results
          .map((result) =>
            "error" in result
              ? `${result.label}: not computed`
              : `${result.label} vol ${result.volatility_pct ?? "n/a"}%, max drawdown ${result.max_drawdown?.depth_pct ?? 0}%`,
          )
          .join("; "),
      };
    },
    render: ({ risk_free_annual_pct, notes, results }) =>
      seriesLines(results, notes, (result) => riskLines(result, risk_free_annual_pct)),
  });
}

const BETAS = z.object({
  risk_free_annual_pct: z.number(),
  /** What the sources say about the series together: the price basis they share, or each one's. */
  notes: z.array(z.string()),
  results: z.array(z.union([z.custom<Relative>((v) => !!v && typeof v === "object" && "beta" in v), FAILED])),
});

export function betaTool() {
  return defineTool({
    name: "beta",
    description:
      "Each asset against a benchmark (such as SPY) on the dates they share: beta of daily returns with its standard " +
      "error, correlation, R squared, annualized alpha, tracking error, information ratio, and each window's return " +
      `against the benchmark's. Give price_history results referenced whole (${referenceTo("e7")}) or series; needs 60 shared ` +
      "returns (3 months or more). The benchmark's history is fetched like the assets', and referenced once its result is back.",
    kind: "compute",
    parallelSafe: true,
    input: z.object({
      benchmark: SERIES,
      assets: z.array(SERIES).min(1).max(9),
      risk_free_annual_pct: RISK_FREE,
    }),
    output: BETAS,
    // One row an asset: its beta and correlation against the benchmark the call's row names.
    preview: [
      hint(BETAS, {
        list: "results",
        fields: ["asset", { field: "beta", label: "beta" }, { field: "correlation", label: "correlation" }],
        except: "error",
        replacesSummary: true,
      }),
    ],
    label: ({ benchmark, assets }) =>
      `${assets.map((one) => labelOf(one)).join(", ")} vs ${labelOf(benchmark)}`,
    async run({ benchmark, assets, risk_free_annual_pct }) {
      const base = prepare(benchmark);
      const sources = assets.map((one) => prepare(one));
      const results = sources.map((asset) => {
        const relative = relativeOf(asset, base, risk_free_annual_pct);
        if ("error" in relative) return { label: asset.label, error: relative.error };
        return { ...relative, notes: [...asset.notes, ...base.notes, ...relative.notes] };
      });
      const to = latestComputed(results);
      return {
        payload: { risk_free_annual_pct, notes: basisNotes([...sources, base]), results },
        provenance: { source: "computed", syncs: true, ...(to ? { as_of: to } : {}) },
        summary: results
          .map((result) =>
            "error" in result
              ? `${result.label}: not computed`
              : `${result.asset} beta ${result.beta.toFixed(2)}`,
          )
          .join("; "),
      };
    },
    render: ({ risk_free_annual_pct, notes, results }) =>
      seriesLines(results, notes, (result) => relativeLines(result, risk_free_annual_pct)),
  });
}

/** The latest date the computed series reach; refuses when none was computed, with each one's reason. */
function latestComputed(
  results: readonly ({ label: string; error: string } | { to: string })[],
): string | undefined {
  if (results.every((result) => "error" in result)) {
    throw new ToolRefusalError(results.map((result) => (result as { error: string }).error).join("; "));
  }
  return results
    .flatMap((result) => ("to" in result ? [result.to] : []))
    .sort()
    .at(-1);
}

/** Each series' lines, one failed said in a line of its own, then the notes on them together. */
function seriesLines<R extends object>(
  results: readonly (R | { label: string; error: string })[],
  notes: readonly string[],
  lines: (result: R) => string[],
): string[] {
  return [
    ...results.flatMap((result) =>
      "error" in result ? [`${result.label}: not computed (${result.error})`] : lines(result as R),
    ),
    ...notes.map((note) => `- note: ${note}`),
  ];
}

const signed = (value: number) => `${value > 0 ? "+" : ""}${value}%`;

export function riskLines(risk: Risk & { sessions_per_year: number }, riskFree: number): string[] {
  const drawdown = risk.max_drawdown;
  return [
    `${risk.label}: ${risk.from} to ${risk.to}, ${risk.returns} daily returns, last close ${risk.last_close}`,
    `- returns: ${[...risk.windows.map((w) => `${w.window} ${signed(w.return_pct)} (from ${w.from})`), `whole series ${signed(risk.total_return_pct)}${risk.annualized_return_pct === null ? "" : ` (annualized ${signed(risk.annualized_return_pct)})`}`].join("; ")}`,
    `- volatility (sample standard deviation of daily returns, annualized by the square root of ${risk.sessions_per_year}): ${risk.volatility_pct === null ? "not computed" : `whole series ${risk.volatility_pct}%`}${risk.volatility_20d_pct === null ? "" : `, last 20 sessions ${risk.volatility_20d_pct}%`}`,
    drawdown
      ? `- deepest drawdown of closes: ${drawdown.depth_pct}% from the peak on ${drawdown.peak} to the trough on ${drawdown.trough}; ${drawdown.recovered ? `back at the peak on ${drawdown.recovered}` : `not recovered as of ${risk.to}`} (within this series)`
      : "- no drawdown: every close is at or above the ones before it",
    ...(risk.var_95_1d_pct === null
      ? []
      : [
          `- 1-day historical VaR at 95%: a loss of ${risk.var_95_1d_pct}% (exceeded on 5% of days); expected shortfall beyond it: ${risk.shortfall_95_1d_pct}%`,
        ]),
    `- best day ${risk.best_day ? `${signed(risk.best_day.return_pct)} on ${risk.best_day.date}` : "none up"}; worst day ${risk.worst_day ? `${signed(risk.worst_day.return_pct)} on ${risk.worst_day.date}` : "none down"}`,
    ...(risk.sharpe === null
      ? []
      : [
          `- Sharpe ratio ${risk.sharpe} (risk-free ${riskFree}% a year; mean daily excess return annualized over annualized volatility)`,
        ]),
    ...(risk.sortino === null
      ? []
      : [
          `- Sortino ratio ${risk.sortino} (the same excess return over the downside deviation: the root mean square of daily shortfalls below the risk-free rate, over every day, annualized)`,
        ]),
    ...(risk.calmar === null
      ? []
      : [
          `- Calmar ratio ${risk.calmar} (annualized return over the depth of the deepest drawdown, both over the whole series)`,
        ]),
    ...risk.notes.map((note) => `- note: ${note}`),
  ];
}

export function relativeLines(relative: Relative, riskFree: number): string[] {
  return [
    `${relative.asset} against ${relative.benchmark}: ${relative.from} to ${relative.to}, ${relative.returns} shared daily returns`,
    `- beta ${relative.beta} (standard error ${relative.beta_se}), correlation ${relative.correlation}, R squared ${relative.r_squared}`,
    `- alpha (the annualized return beyond what beta explains, not the total return) ${signed(relative.alpha_pct)} (risk-free ${riskFree}%); tracking error ${relative.tracking_error_pct}%; information ratio ${relative.information_ratio ?? "not defined"}`,
    `- against ${relative.benchmark}: ${relative.excess.map((w) => `${w.window} ${signed(w.excess_pct)} (${signed(w.asset_pct)} vs ${signed(w.benchmark_pct)}, from ${w.from})`).join("; ")}`,
    ...relative.notes.map((note) => `- note: ${note}`),
  ];
}
