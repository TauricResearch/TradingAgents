// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Every environment variable the app reads at runtime, by setting. The terminal's own conventions
 * (colour, locale) are read where the theme is chosen.
 */
import { APP_NAME, type HostedProvider } from "../contracts/index.js";

/** `TRADINGAGENTS_<NAME>`: the environment variable for one setting. */
export function envName(name: string): string {
  return `${APP_NAME.toUpperCase().replace(/[^A-Z0-9]/g, "_")}_${name}`;
}

/** The environment variables, by setting. */
export const ENV = {
  home: envName("HOME"),
  baseURL: envName("BASE_URL"),
  model: envName("MODEL"),
  modelKey: envName("MODEL_API_KEY"),
  tauricKey: "TAURIC_API_KEY",
  sync: envName("SYNC"),
  /** Set to anything: no check for a newer release. */
  noUpdateCheck: envName("NO_UPDATE_CHECK"),
} as const;

/** Where each hosted provider's key is looked for in the environment, in order: the first set is used. */
export const KEY_VARS: { readonly [P in HostedProvider]: readonly string[] } = {
  tauric: [ENV.tauricKey],
  openai: ["OPENAI_API_KEY"],
  anthropic: ["ANTHROPIC_API_KEY"],
  google: ["GEMINI_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY", "GOOGLE_API_KEY"],
  deepseek: ["DEEPSEEK_API_KEY"],
  openrouter: ["OPENROUTER_API_KEY"],
  llmtr: ["LLMTR_API_KEY"],
};
