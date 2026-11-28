// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The models offered for each hosted provider, best value first, and what is known about each: its
 * metadata is generated from a pinned models.dev snapshot, never fetched at run time,
 * except for a model models.dev does not list, whose facts come from its provider's API reference. The
 * lists are curated.
 */
import { REASONING_LEVELS, type ReasoningLevel } from "../contracts/index.js";
import generated from "./catalog.generated.json" with { type: "json" };
import providerFacts from "./provider-facts.json" with { type: "json" };

/** Hosted providers with a curated list; a compatible server's models are its own. */
export const CATALOG_PROVIDERS = [
  "tauric",
  "chatgpt",
  "openai",
  "anthropic",
  "google",
  "deepseek",
  "openrouter",
  "llmtr",
] as const;
export type CatalogProvider = (typeof CATALOG_PROVIDERS)[number];

/** A model's place in its provider's list: the default, an alternative, or the fast tier for light work. */
export type Role = "default" | "alt" | "fast";

export const CATALOG: { readonly [P in CatalogProvider]: readonly { id: string; role: Role }[] } = {
  // One model, for every kind of work.
  tauric: [{ id: "tauric", role: "default" }],
  chatgpt: [
    { id: "gpt-6.2-sol", role: "default" },
    { id: "gpt-6.2-astra", role: "alt" },
    { id: "gpt-6.1-terra", role: "alt" },
    { id: "gpt-6-luna", role: "fast" },
  ],
  openai: [
    { id: "gpt-6.2-sol", role: "default" },
    { id: "gpt-6.2-astra", role: "alt" },
    { id: "gpt-6.1-terra", role: "alt" },
    { id: "gpt-6-luna", role: "fast" },
  ],
  anthropic: [
    { id: "claude-sonnet-5-5", role: "default" },
    { id: "claude-opus-5-5", role: "alt" },
    { id: "claude-fable-5-2", role: "alt" },
    { id: "claude-haiku-5-5", role: "fast" },
  ],
  google: [
    { id: "gemini-4-argon", role: "default" },
    { id: "gemini-4-neon", role: "alt" },
    { id: "gemini-4-carbon", role: "alt" },
    { id: "gemini-4-hydrogen", role: "fast" },
  ],
  deepseek: [
    { id: "deepseek-v4-pro", role: "default" },
    { id: "deepseek-flash", role: "fast" },
  ],
  openrouter: [
    { id: "anthropic/claude-sonnet-5.5", role: "default" },
    { id: "openai/gpt-6.2-sol", role: "alt" },
    { id: "google/gemini-4-argon", role: "alt" },
    { id: "anthropic/claude-haiku-5.5", role: "fast" },
  ],
  // IDs are vendor/model as the account can use; any other id can be passed as llmtr/<id>.
  llmtr: [
    { id: "qwen/qwen3.8-flash", role: "default" },
    { id: "qwen/qwen3.8-max", role: "alt" },
    { id: "minimax/minimax-m3.1-flash", role: "fast" },
  ],
};

/** Where each provider's metadata comes from in models.dev: a plan's models are OpenAI's. */
export const METADATA_SOURCE: { readonly [P in CatalogProvider]: string } = {
  tauric: "tauric",
  chatgpt: "openai",
  openai: "openai",
  anthropic: "anthropic",
  google: "google",
  deepseek: "deepseek",
  openrouter: "openrouter",
  llmtr: "llmtr",
};

/** What the catalog knows of a model. */
export type ModelInfo = {
  name: string;
  /** Context window in tokens, and the most a request may send when that is less. */
  context: number;
  input?: number;
  /** The most one response may write. */
  output: number;
  /** US dollars per million tokens. */
  cost?: { input: number; output: number };
  /**
   * The reasoning levels the model takes, "none" first where it can skip reasoning; empty when it
   * does not reason, null when models.dev does not say.
   */
  reasoning: string[] | null;
};

/**
 * Models models.dev does not list, by "source/id": their facts from the provider's API reference, kept as
 * data (provider-facts.json) beside the generated metadata. A user's contextWindow setting still wins.
 */
export const PROVIDER_FACTS = providerFacts as { readonly [model: string]: ModelInfo };

const INFO: { readonly [model: string]: ModelInfo } = {
  ...(generated as unknown as { readonly [model: string]: ModelInfo }),
  ...PROVIDER_FACTS,
};

/** The catalog's facts about `provider`'s model `id`, if it lists it. */
export function modelInfo(provider: CatalogProvider, id: string): ModelInfo | undefined {
  return INFO[`${METADATA_SOURCE[provider]}/${id}`];
}

/** The levels the catalog lists for `provider`'s model `id`, least first (a list may come in any order, with unknown names). */
export function offeredLevels(provider: string, id: string): (typeof REASONING_LEVELS)[number][] {
  const info = (CATALOG_PROVIDERS as readonly string[]).includes(provider)
    ? modelInfo(provider as CatalogProvider, id)
    : undefined;
  return REASONING_LEVELS.filter((level) => info?.reasoning?.includes(level));
}

/**
 * The least `provider`'s model `id` reasons at: the first level the catalog lists for it ("none" where it
 * can skip reasoning), else the provider's default when the catalog does not know.
 */
export function leastReasoning(provider: string, id: string): ReasoningLevel {
  return offeredLevels(provider, id)[0] ?? "provider-default";
}

/**
 * `level` as `provider`'s model `id` can be asked for it: itself when the model offers it, else the
 * nearest level above it, else the model's most. The provider's default, and any level for a model the
 * catalog does not know, are left as they are.
 */
export function fitReasoning(provider: string, id: string, level: ReasoningLevel): ReasoningLevel {
  const offered = offeredLevels(provider, id);
  if (level === "provider-default" || offered.length === 0 || offered.includes(level)) return level;
  const at = REASONING_LEVELS.indexOf(level as (typeof REASONING_LEVELS)[number]);
  return offered.find((candidate) => REASONING_LEVELS.indexOf(candidate) > at) ?? offered.at(-1) ?? level;
}
