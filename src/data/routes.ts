// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The one place that says which providers serve each capability, in order: Tauric first, then Yahoo
 * where Yahoo serves it (quotes and daily price history); prediction-market odds come from Polymarket.
 * A provider that is not configured, or does not implement the method asked, is skipped.
 */
import type { Capability } from "./capabilities.js";

export type ProviderName = "tauric" | "yahoo" | "polymarket";

export const ROUTES: { readonly [Name in Capability]: readonly ProviderName[] } = {
  quotes: ["tauric", "yahoo"],
  priceHistory: ["tauric", "yahoo"],
  statements: ["tauric"],
  filings: ["tauric"],
  news: ["tauric"],
  profiles: ["tauric"],
  ownership: ["tauric"],
  corporateActions: ["tauric"],
  technicals: ["tauric"],
  macroSeries: ["tauric"],
  instruments: ["tauric"],
  syntheses: ["tauric"],
  crossSections: ["tauric"],
  markets: ["tauric"],
  predictionMarkets: ["polymarket"],
};
