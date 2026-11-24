// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Models served through an OpenAI-compatible chat completions endpoint: vLLM, Ollama, LM Studio
 * and the hosted services that speak the same API. The endpoint comes from configuration.
 */

import { createOpenAICompatible } from "@ai-sdk/openai-compatible";
import { endpointOf, type ModelClient } from "../contracts/index.js";
import { REQUEST_MS } from "../contracts/limits.js";
import { AiSdkModelClient } from "./ai-sdk.js";

/** The key a server's raw request options are sent under (the SDK reads it up to its first dot). */
const NAME = "model";

type OpenAICompatibleConfig = {
  baseURL: string;
  model: string;
  apiKey?: string;
  /**
   * How the server switches a model's thinking on and off. "chat-template" sends vLLM's
   * chat_template_kwargs.enable_thinking (Qwen and similar templates).
   */
  thinkingSwitch?: "chat-template" | "none";
  fetch?: typeof globalThis.fetch;
  /** How long a request may send nothing before it is ended as stalled. */
  stallMs?: number;
};

/** Who a server's replay data may be sent back to: its endpoint and model. */
export function compatibleReplayKey(server: { baseURL: string; model: string }): string {
  return `openai-compatible ${endpointOf(server.baseURL)} ${server.model}`;
}

export function openAICompatibleClient(config: OpenAICompatibleConfig): ModelClient {
  const provider = createOpenAICompatible({
    name: NAME,
    baseURL: config.baseURL,
    includeUsage: true,
    ...(config.apiKey ? { apiKey: config.apiKey } : {}),
    ...(config.fetch ? { fetch: config.fetch } : {}),
  });
  return new AiSdkModelClient(
    provider.chatModel(config.model),
    config.model,
    (request) => {
      const { topK, thinking, ...sampling } = request.sampling ?? {};
      const raw: Record<string, number | { enable_thinking: boolean }> = {};
      if (topK !== undefined) raw.top_k = topK; // the SDK maps no top_k for this provider
      if (thinking !== undefined && config.thinkingSwitch === "chat-template") {
        raw.chat_template_kwargs = { enable_thinking: thinking };
      }
      return Object.keys(raw).length ? { sampling, providerOptions: { [NAME]: raw } } : { sampling };
    },
    config.stallMs,
    { replayKey: compatibleReplayKey(config) },
  );
}

/**
 * The context window the server reports for `model` (vLLM lists it as `max_model_len`), or undefined
 * when it reports none or cannot be asked within a few seconds.
 */
export async function serverContextWindow(
  config: Pick<OpenAICompatibleConfig, "baseURL" | "model" | "apiKey" | "fetch">,
): Promise<number | undefined> {
  try {
    const response = await (config.fetch ?? fetch)(`${config.baseURL.replace(/\/$/, "")}/models`, {
      headers: config.apiKey ? { Authorization: `Bearer ${config.apiKey}` } : {},
      signal: AbortSignal.timeout(REQUEST_MS.modelProbe),
    });
    if (!response.ok) return undefined;
    const body = (await response.json()) as { data?: { id?: unknown; max_model_len?: unknown }[] };
    const entry = body.data?.find((item) => item.id === config.model);
    const window = entry?.max_model_len;
    return typeof window === "number" && Number.isInteger(window) && window > 0 ? window : undefined;
  } catch {
    return undefined;
  }
}
