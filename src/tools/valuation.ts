// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Valuation: a discounted cash flow from a company's profile and cash flow statement (referenced whole)
 * or figures given directly, and its multiples against named peers.
 */
import { z } from "zod";
import { round } from "../compute/series.js";
import { type Dcf, dcfOf, type Wacc, waccOf } from "../compute/valuation.js";
import { message } from "../contracts/index.js";
import type { Profiles } from "../data/capabilities.js";
import { PROFILE } from "./company.js";
import { referenceTo } from "./references.js";
import { STATEMENT } from "./statements.js";
import { defineTool, ToolRefusalError, wholeResult } from "./tool.js";
import { amount, displayNumber, provenanceOf, symbol } from "./tool-text.js";

const percent = (what: string) => z.number().min(-50).max(100).describe(`${what}, in percent (9 is 9%)`);

const DISCOUNT = z.union([
  z.object({ rate_pct: percent("The discount rate a year") }).strict(),
  z
    .object({
      risk_free_pct: percent("The risk-free rate, such as the 10-year Treasury yield"),
      beta: z.number().min(-1).max(5).describe("Beta against the market, such as from the beta tool"),
      equity_risk_premium_pct: percent("The equity risk premium you assume, often 4 to 6"),
      cost_of_debt_pct: percent("The pre-tax cost of debt you assume, such as interest paid over debt"),
      tax_rate_pct: percent("The tax rate"),
    })
    .strict(),
]);

/** Cash flow statement lines a DCF reads, by the names Tauric gives them. */
const LINES = {
  operating: ["Net Cash from Operating Activities"],
  capex: ["Payments to Acquire PP&E", "Payments to Acquire Productive Assets"],
  interest: ["Interest Paid, Excluding Capitalized Interest, Operating Activities"],
  compensation: ["Share-Based Compensation"],
};

type Used = { name: string; value: number; from: string };

export function dcfTool() {
  return defineTool({
    name: "dcf",
    description:
      `Value a company by discounting its free cash flow. Give its profile (${referenceTo("e3")}: market cap, debt, ` +
      `cash, shares) and its annual cash flow statement (${referenceTo("e4")}: operating cash flow less ` +
      "capital expenditure), or the figures directly; up to two growth stages; a terminal growth rate; and the " +
      "discount rate, or the inputs of a WACC (risk-free rate, beta, equity risk premium, cost of debt, tax rate). " +
      "Returns the enterprise and equity value against the market cap, per-share value, and a sensitivity grid.",
    kind: "compute",
    parallelSafe: true,
    input: z.object({
      profile: wholeResult("The company's profile result").optional(),
      cash_flow: wholeResult("Its annual cash flow statement result").optional(),
      base_fcf: z
        .number()
        .optional()
        .describe("The free cash flow of the last year, instead of the statement's"),
      flows: z
        .array(z.number())
        .min(1)
        .max(15)
        .optional()
        .describe("Each year's free cash flow, instead of growing a base"),
      stages: z
        .array(z.object({ years: z.number().int().min(1).max(10), growth_pct: percent("Growth a year") }))
        .max(2)
        .default([])
        .describe("Up to two growth stages from the base, such as 5 years at 12% then 5 at 6%"),
      terminal_growth_pct: percent("Growth a year after the last stage, below the discount rate"),
      discount: DISCOUNT,
      net_debt: z.number().optional().describe("Debt less cash, instead of the profile's"),
      shares: z.number().positive().optional().describe("Shares outstanding, instead of the profile's"),
      mid_year: z.boolean().default(false).describe("Discount each year's flow at mid-year"),
    }),
    output: z.object({
      inputs: z.array(z.object({ name: z.string(), value: z.number(), from: z.string() })),
      wacc: z.custom<Wacc>().nullable(),
      discount_pct: z.number(),
      terminal_growth_pct: z.number(),
      mid_year: z.boolean(),
      currency: z.string().nullable(),
      dcf: z.custom<Dcf>(),
      notes: z.array(z.string()),
    }),
    label: ({ profile, cash_flow, terminal_growth_pct }) => {
      const symbol = [profile, cash_flow]
        .map((one) => (one as { symbol?: unknown } | undefined)?.symbol)
        .find((one) => typeof one === "string");
      return `${symbol ? `${symbol}, ` : ""}terminal growth ${terminal_growth_pct}%`;
    },
    async run(input) {
      const used: Used[] = [];
      const notes: string[] = [];
      const profile = input.profile === undefined ? undefined : PROFILE.safeParse(input.profile);
      if (profile && !profile.success)
        throw new ToolRefusalError("profile must be a profile result, referenced whole");
      const facts = profile?.data.facts ?? {};
      const fact = (name: string) => (typeof facts[name] === "number" ? (facts[name] as number) : undefined);
      // Market values and cash flows must be in one currency.
      const currency = profile?.data.currency ?? null;
      const reported = typeof facts.financial_currency === "string" ? facts.financial_currency : undefined;
      if (currency && reported && reported !== currency) {
        throw new ToolRefusalError(
          `the company reports in ${reported} and trades in ${currency}; give its free cash flow and net debt in ${currency} directly`,
        );
      }

      // The base: given, or operating cash flow less capital expenditure from the statement.
      let base = input.base_fcf;
      let interest: number | undefined;
      if (base !== undefined) used.push({ name: "base free cash flow", value: base, from: "given" });
      else if (!input.flows && input.cash_flow !== undefined) {
        const statement = STATEMENT.safeParse(input.cash_flow);
        if (!statement.success || statement.data.statement !== "cash_flow") {
          throw new ToolRefusalError("cash_flow must be a cash flow statement result, referenced whole");
        }
        const period = statement.data.periods[0];
        if (!period) throw new ToolRefusalError("the cash flow statement has no period");
        const from = `${statement.data.period_type} cash flow ${period.start ? `${period.start} to ` : ""}${period.end}`;
        const pick = (names: string[]) =>
          period.lines.find((line) => names.includes(line.line) && line.value !== null);
        const operating = pick(LINES.operating);
        const capex = pick(LINES.capex);
        if (!operating || !capex) {
          throw new ToolRefusalError(
            `the statement lacks ${operating ? "capital expenditure" : "operating cash flow"}; give base_fcf instead`,
          );
        }
        // Capital expenditure is a payment: whichever sign it is filed with, it reduces the flow.
        base = (operating.value as number) - Math.abs(capex.value as number);
        used.push(
          { name: operating.line, value: operating.value as number, from },
          { name: capex.line, value: capex.value as number, from },
        );
        const paid = pick(LINES.interest);
        if (paid) interest = Math.abs(paid.value as number);
        const compensation = pick(LINES.compensation);
        if (compensation) {
          notes.push(
            `share-based compensation (${amount(compensation.value)}) is not deducted from the free cash flow`,
          );
        }
        if (statement.data.period_type === "quarterly")
          notes.push(
            "the base is one quarter's flow; use the annual statement, or give base_fcf as the sum of the last four quarters",
          );
      }

      // The discount rate: given, or the WACC of the inputs with the profile's market values as weights.
      let wacc: Wacc | null = null;
      let discount: number;
      if ("rate_pct" in input.discount) discount = input.discount.rate_pct;
      else {
        const equity = fact("market_cap");
        const debt = fact("total_debt") ?? 0;
        if (equity === undefined)
          throw new ToolRefusalError("a WACC needs the market cap: give the profile, or rate_pct");
        const derived = waccOf({ ...input.discount, equity_value: equity, debt_value: debt });
        if ("error" in derived) throw new ToolRefusalError(derived.error);
        wacc = derived;
        discount = derived.wacc_pct;
        // Operating cash flow is after interest: adding back the after-tax interest makes it the flow to the firm.
        if (base !== undefined && interest !== undefined) {
          const addBack = interest * (1 - input.discount.tax_rate_pct / 100);
          base += addBack;
          used.push({
            name: "after-tax interest paid, added back",
            value: Math.round(addBack),
            from: "the cash flow statement",
          });
        }
      }
      if (interest === undefined && !input.flows) {
        notes.push(
          "the flow is after interest (levered) while it is discounted as the firm's: it understates the value somewhat",
        );
      }

      const netDebt =
        input.net_debt ??
        (fact("total_debt") !== undefined || fact("total_cash") !== undefined
          ? (fact("total_debt") ?? 0) - (fact("total_cash") ?? 0)
          : undefined);
      if (netDebt === undefined)
        throw new ToolRefusalError("give net_debt, or the profile with debt and cash");
      used.push({
        name: "net debt",
        value: netDebt,
        from: input.net_debt === undefined ? "the profile's total debt less total cash" : "given",
      });
      if (input.net_debt === undefined)
        notes.push("net debt leaves out leases, minority interests and preferred stock");
      const shares = input.shares ?? fact("shares_outstanding");
      if (shares !== undefined)
        used.push({
          name: "shares",
          value: shares,
          from: input.shares === undefined ? "the profile" : "given",
        });
      if (input.shares === undefined && facts.market_cap_basis === "stated") {
        notes.push(
          "the company has several share classes: compare the equity value with the market cap rather than the value per share",
        );
      }
      const marketCap = fact("market_cap");
      const g = input.terminal_growth_pct;
      const result = dcfOf({
        ...(input.flows ? { flows: input.flows } : {}),
        ...(base !== undefined ? { base, stages: input.stages } : {}),
        terminal_growth_pct: g,
        discount_pct: discount,
        net_debt: netDebt,
        ...(shares !== undefined ? { shares } : {}),
        ...(marketCap !== undefined ? { market_cap: marketCap } : {}),
        mid_year: input.mid_year,
        grid: {
          discount_pcts: [discount - 1, discount, discount + 1].map((r) => Number(r.toFixed(2))),
          growth_pcts: [g - 0.5, g, g + 0.5].map((x) => Number(x.toFixed(2))),
        },
      });
      if ("error" in result) throw new ToolRefusalError(result.error);
      return {
        payload: {
          inputs: used,
          wacc,
          discount_pct: discount,
          terminal_growth_pct: g,
          mid_year: input.mid_year,
          currency,
          dcf: result,
          notes: [...notes, ...result.notes],
        },
        provenance: { source: "computed", syncs: true },
        summary: `equity value ${displayNumber(result.equity_value)}${result.vs_market_cap_pct === null ? "" : `, ${result.vs_market_cap_pct > 0 ? "+" : ""}${result.vs_market_cap_pct}% against the market cap`}`,
      };
    },
    render(answer) {
      const { dcf, wacc } = answer;
      const money = (value: number) => `${amount(value)}${answer.currency ? ` ${answer.currency}` : ""}`;
      return [
        `inputs: ${answer.inputs.map((used) => `${used.name} ${amount(used.value)} (${used.from})`).join("; ")}`,
        wacc
          ? `discount rate: WACC ${wacc.wacc_pct}% (cost of equity ${wacc.cost_of_equity_pct}%, after-tax cost of debt ${wacc.after_tax_cost_of_debt_pct}%, weights ${wacc.equity_weight} equity and ${wacc.debt_weight} debt by market value)`
          : `discount rate: ${answer.discount_pct}% (given)`,
        `flows (${answer.mid_year ? "discounted at mid-year" : "discounted at each year's end"}): ${dcf.flows.map((row) => `year ${row.year} ${amount(row.flow)} (present value ${amount(row.present_value)})`).join("; ")}`,
        `terminal value at ${answer.terminal_growth_pct}% growth: ${money(dcf.terminal_value)}, present value ${money(dcf.present_value_of_terminal)} (${dcf.terminal_share_pct}% of the enterprise value)`,
        `enterprise value ${money(dcf.enterprise_value)}; equity value ${money(dcf.equity_value)}${dcf.vs_market_cap_pct === null ? "" : `, ${dcf.vs_market_cap_pct > 0 ? "+" : ""}${dcf.vs_market_cap_pct}% against the market cap`}${dcf.per_share === null ? "" : `; ${dcf.per_share} per share`}`,
        ...(dcf.grid
          ? [
              `equity value by discount rate (rows) and terminal growth (columns ${dcf.grid.growth_pcts.map((x) => `${x}%`).join(", ")}):`,
              ...dcf.grid.discount_pcts.map(
                (r, i) =>
                  `  ${r}%: ${(dcf.grid?.equity_values[i] ?? []).map((v) => (v === null ? "n/a" : amount(v))).join(", ")}`,
              ),
            ]
          : []),
        ...answer.notes.map((note) => `note: ${note}`),
      ];
    },
  });
}

/** The multiples a profile gives, by name, and the words for each. */
const MULTIPLES = {
  pe_ratio: "P/E (trailing)",
  forward_pe: "P/E (forward)",
  peg_ratio: "PEG",
  price_to_book: "price to book",
  price_to_sales: "price to sales",
} as const;
type Multiple = keyof typeof MULTIPLES;
/** Peers with a usable multiple needed for a median. */
const LEAST_PEERS = 3;

const ROW = z.object({
  multiple: z.string(),
  target: z.number().nullable(),
  median: z.number().nullable(),
  low: z.number().nullable(),
  high: z.number().nullable(),
  peers: z.number(),
  /** The target's value at the peers' median multiple, against today's, in percent. */
  implied_change_pct: z.number().nullable(),
});

export function compsTool(profiles: Profiles) {
  return defineTool({
    name: "comps",
    description:
      "A company's valuation multiples against 3 to 8 peers you name (such as companies in its sub-industry): " +
      "trailing and forward P/E, PEG, price to book and price to sales, each with the peers' median and range, " +
      "and the change in the company's value at the peers' median.",
    kind: "data",
    parallelSafe: true,
    input: z.object({ symbol, peers: z.array(symbol).min(3).max(8) }),
    output: z.object({
      symbol: z.string(),
      peers: z.array(z.string()),
      /** Peers whose profile could not be read, and why. */
      missing: z.array(z.string()),
      rows: z.array(ROW),
      notes: z.array(z.string()),
    }),
    label: ({ symbol, peers }) => `${symbol} vs ${peers.join(", ")}`,
    async run({ symbol: target, peers }, { signal }) {
      const names = [target, ...peers.filter((peer) => peer !== target)];
      const read = await Promise.allSettled(names.map((name) => profiles.profile(name, { signal })));
      const first = read[0];
      if (!first || first.status === "rejected") throw first?.reason;
      const answers = read.flatMap((one, i) =>
        one.status === "fulfilled" ? [{ name: names[i] as string, answer: one.value }] : [],
      );
      const missing = read.flatMap((one, i) =>
        one.status === "rejected"
          ? [`${names[i]}: ${one.reason instanceof Error ? one.reason.message : String(one.reason)}`]
          : [],
      );
      const notes: string[] = [];
      const multipleOf = (data: Record<string, unknown>, multiple: Multiple) => {
        const value = data[multiple];
        return typeof value === "number" && Number.isFinite(value) ? value : null;
      };
      const rows = (Object.keys(MULTIPLES) as Multiple[]).map((multiple) => {
        const own = multipleOf(first.value.data, multiple);
        // A multiple at or below zero (a loss, negative book) says nothing about value.
        const values = answers
          .slice(1)
          .map(({ name, answer }) => ({ name, value: multipleOf(answer.data, multiple) }))
          .filter((one): one is { name: string; value: number } => one.value !== null && one.value > 0);
        for (const one of values) {
          if (multiple === "pe_ratio" && one.value > 100)
            notes.push(`${one.name}'s trailing P/E of ${one.value} is above 100`);
        }
        const sorted = values.map((one) => one.value).sort((a, b) => a - b);
        const median = sorted.length >= LEAST_PEERS ? middle(sorted) : null;
        return {
          multiple: MULTIPLES[multiple],
          target: own,
          median: median === null ? null : round(median),
          low: sorted.length ? round(sorted[0] as number) : null,
          high: sorted.length ? round(sorted.at(-1) as number) : null,
          peers: sorted.length,
          implied_change_pct:
            median !== null && own !== null && own > 0 ? round((median / own - 1) * 100, 1) : null,
        };
      });
      if (rows.some((row) => row.median === null)) {
        notes.push(
          `a median needs at least ${LEAST_PEERS} peers with a positive multiple; where fewer have one, none is given`,
        );
      }
      const sources = [...new Set(answers.map(({ answer }) => answer.source))];
      return {
        payload: { symbol: target, peers: names.slice(1), missing, rows, notes },
        provenance: provenanceOf(
          {
            source: sources.join(", "),
            after: [...new Set(answers.flatMap(({ answer }) => answer.after))],
            notes: [],
            ...(answers.every(({ answer }) => answer.syncs) ? { syncs: true as const } : {}),
          },
          { subject: target },
        ),
        summary: message("tool.comps", { count: answers.length - 1 }),
      };
    },
    render(answer) {
      return [
        `${answer.symbol} against ${answer.peers.join(", ")}: multiple, ${answer.symbol}, peers' median (how many), range, ${answer.symbol}'s value at the median`,
        ...answer.rows.map(
          (row) =>
            `- ${row.multiple}: ${row.target ?? "n/a"}, median ${row.median ?? "n/a"} (${row.peers}), range ${row.low ?? "n/a"} to ${row.high ?? "n/a"}, ${row.implied_change_pct === null ? "no implied value" : `${row.implied_change_pct > 0 ? "+" : ""}${row.implied_change_pct}%`}`,
        ),
        ...answer.missing.map((line) => `not read: ${line}`),
        ...answer.notes.map((note) => `note: ${note}`),
      ];
    },
  });
}

function middle(sorted: number[]): number {
  const half = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? (sorted[half] as number)
    : ((sorted[half - 1] as number) + (sorted[half] as number)) / 2;
}
