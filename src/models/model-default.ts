// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** The model a run uses when none is chosen. */

import { PROVIDER_IDS, type ProviderId, type ReasoningLevel } from "../contracts/index.js";
import {
  CATALOG,
  CATALOG_PROVIDERS,
  type CatalogProvider,
  modelInfo,
  offeredLevels,
  type Role,
} from "./catalog.js";
/** The provider a first setup recommends: Tauric, whose one key serves both data and a model. */
export const RECOMMENDED: ProviderId = "tauric";

/** A provider's default model as "provider/id", when the catalog lists one. */
export function defaultOf(provider: ProviderId): string | undefined {
  const listed = (CATALOG as Partial<Record<ProviderId, readonly { id: string; role: string }[]>>)[provider];
  const id = listed?.find((model) => model.role === "default")?.id;
  return id === undefined ? undefined : `${provider}/${id}`;
}

/**
 * With no model chosen: the default of the one provider that can be used (Tauric only when no other
 * can), else the providers to choose from (none, or several).
 */
export function defaultModel(usable: readonly ProviderId[]): { model: string } | { choices: ProviderId[] } {
  const choices = PROVIDER_IDS.filter(
    (provider) => usable.includes(provider) && defaultOf(provider) !== undefined,
  );
  // A Tauric key also serves data: beside one other provider, that one's model is used.
  const others = choices.filter((provider) => provider !== "tauric");
  const pool = others.length ? others : choices;
  const only = pool.length === 1 ? defaultOf(pool[0] as CatalogProvider) : undefined;
  return only ? { model: only } : { choices: pool };
}

/** A model a provider offers, as a picker shows it. */
export type ModelOption = {
  id: string;
  name: string;
  /** The provider's default, an alternative, or its fast model for light work. */
  role: Role;
  /** Whose model it is, where a provider serves several families' (OpenRouter's "anthropic/..."). */
  family?: string;
  context?: number;
  /** US dollars per million tokens in and out. */
  cost?: { input: number; output: number };
  reasoning: ReasoningLevel[];
};

/** The models the catalog lists for `provider`, each with its role; OpenRouter's and LLMTR's grouped by family. */
export function modelsOf(provider: ProviderId): ModelOption[] {
  if (!(CATALOG_PROVIDERS as readonly string[]).includes(provider)) return [];
  const options = CATALOG[provider as CatalogProvider].map(({ id, role }): ModelOption => {
    const info = modelInfo(provider as CatalogProvider, id);
    const family =
      provider === "openrouter" || provider === "llmtr" ? id.slice(0, id.indexOf("/")) : undefined;
    return {
      id,
      name: info?.name ?? id,
      role,
      ...(family ? { family } : {}),
      ...(info?.context ? { context: info.context } : {}),
      ...(info?.cost ? { cost: info.cost } : {}),
      reasoning: offeredLevels(provider, id),
    };
  });
  // A family's models together, the families in the order the list first names them (the default's first).
  const families = [...new Set(options.map((option) => option.family))];
  return options
    .map((option, at) => ({ option, at }))
    .sort((a, b) => families.indexOf(a.option.family) - families.indexOf(b.option.family) || a.at - b.at)
    .map(({ option }) => option);
}
