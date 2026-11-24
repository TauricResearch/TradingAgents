// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** The data tools an agent may be given, each with the capability it reads, and the compute tools. */
import type { Clock } from "../contracts/index.js";
import type { Capabilities, Capability } from "../data/capabilities.js";
import { calcTool } from "./calc.js";
import { estimatesTool, ownershipTool, profileTool } from "./company.js";
import { corporateActionsTool } from "./corporate-actions.js";
import { correlationTool } from "./correlation.js";
import { filingSectionTool, filingsTool } from "./filings.js";
import { indicatorsTool } from "./indicators.js";
import { findInstrumentTool } from "./instruments.js";
import { macroSeriesTool } from "./macro.js";
import { marketsTool } from "./markets.js";
import { articleTool, newsTool } from "./news.js";
import { optimizePortfolioTool } from "./optimize.js";
import { portfolioRiskTool } from "./portfolio.js";
import { predictionMarketsTool } from "./prediction-markets.js";
import { priceHistoryTool } from "./price-history.js";
import { quoteTool } from "./quote.js";
import { betaTool, returnsRiskTool } from "./risk.js";
import { screenTool } from "./screen.js";
import { statementsTool } from "./statements.js";
import { tauricViewTool } from "./tauric-view.js";
import { technicalsTool } from "./technicals.js";
import type { Tool } from "./tool.js";
import { compsTool, dcfTool } from "./valuation.js";

/** A data tool as the catalog lists it: its name, the capability it reads, and how it is made from that. */
type DataToolEntry = {
  name: string;
  capability: Capability;
  make(data: Capabilities, clock: Clock): Tool;
};

/** The data tools: every one is offered, whichever sources serve it. */
export const DATA_TOOLS: readonly DataToolEntry[] = [
  { name: "quote", capability: "quotes", make: (data) => quoteTool(data.quotes) },
  {
    name: "price_history",
    capability: "priceHistory",
    make: (data, clock) => priceHistoryTool(data.priceHistory, clock),
  },
  { name: "statements", capability: "statements", make: (data) => statementsTool(data.statements) },
  { name: "filings", capability: "filings", make: (data) => filingsTool(data.filings) },
  { name: "filing_section", capability: "filings", make: (data) => filingSectionTool(data.filings) },
  { name: "news", capability: "news", make: (data) => newsTool(data.news) },
  { name: "article", capability: "news", make: (data) => articleTool(data.news) },
  { name: "profile", capability: "profiles", make: (data) => profileTool(data.profiles) },
  { name: "estimates", capability: "profiles", make: (data) => estimatesTool(data.profiles) },
  { name: "comps", capability: "profiles", make: (data) => compsTool(data.profiles) },
  { name: "ownership", capability: "ownership", make: (data) => ownershipTool(data.ownership) },
  {
    name: "corporate_actions",
    capability: "corporateActions",
    make: (data) => corporateActionsTool(data.corporateActions),
  },
  { name: "technicals", capability: "technicals", make: (data) => technicalsTool(data.technicals) },
  { name: "macro_series", capability: "macroSeries", make: (data) => macroSeriesTool(data.macroSeries) },
  {
    name: "find_instrument",
    capability: "instruments",
    make: (data) => findInstrumentTool(data.instruments),
  },
  { name: "markets", capability: "markets", make: (data) => marketsTool(data.markets) },
  { name: "tauric_view", capability: "syntheses", make: (data) => tauricViewTool(data.syntheses) },
  {
    name: "screen",
    capability: "crossSections",
    make: (data, clock) => screenTool(data.crossSections, clock),
  },
  {
    name: "prediction_markets",
    capability: "predictionMarkets",
    make: (data, clock) => predictionMarketsTool(data.predictionMarkets, clock),
  },
];

/** The names of the data tools, which agents may name. */
export function dataToolNames(): string[] {
  return DATA_TOOLS.map((entry) => entry.name);
}

/** The data tools made from `data`, each with the capability it reads. */
export function dataTools(data: Capabilities, clock: Clock): [Capability, Tool][] {
  return DATA_TOOLS.map((entry) => [entry.capability, entry.make(data, clock)]);
}

/** The compute tools: arithmetic and statistics over values and recorded results, read from no source. */
export function computeTools(): Tool[] {
  return [
    calcTool(),
    correlationTool(),
    returnsRiskTool(),
    betaTool(),
    portfolioRiskTool(),
    optimizePortfolioTool(),
    indicatorsTool(),
    dcfTool(),
  ];
}
