// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** Polymarket as a provider: open prediction markets and their odds. */
import type { DataProvider } from "../capabilities.js";
import type { PolymarketClient } from "./client.js";

export function polymarketProvider(client: PolymarketClient): DataProvider {
  return {
    name: "Polymarket",
    capabilities: { predictionMarkets: { search: (topic, now, call) => client.search(topic, now, call) } },
  };
}
