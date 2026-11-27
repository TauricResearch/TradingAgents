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

type ServerQuery = Pick<OpenAICompatibleConfig, "baseURL" | "model" | "apiKey" | "fetch">;

/**
 * The fields a model list may give a model's window in: vLLM and SGLang's `max_model_len`, and the
 * `context_length`, `context_window` and `max_context_length` of hosted services (OpenRouter, Together,
 * Groq, Mistral). A training length (llama.cpp's `meta.n_ctx_train`) is not one: the server may run less.
 */
const LISTED_WINDOW = ["max_model_len", "context_length", "context_window", "max_context_length"] as const;

/**
 * The context window the server runs `model` with, or undefined when it reports none or cannot be
 * asked within a few seconds. The model list is read first; a server that lists no window there is
 * asked in its own API: llama.cpp's `/props`, a running Ollama model's `/api/ps`, a loaded LM Studio
 * model's `/api/v1/models`. Only the window a server runs with is taken, never the model's trained
 * maximum, which a server started with less would cut a request short of.
 */
export async function serverContextWindow(config: ServerQuery): Promise<number | undefined> {
  const base = config.baseURL.replace(/\/+$/, "");
  const list = await getJson(config, `${base}/models`);
  // No list (the server is down, or refused the key): nothing else there will answer either.
  if (list === undefined) return undefined;
  const entry = listedModel(list, config.model);
  for (const field of LISTED_WINDOW) {
    const window = tokens(entry?.[field]);
    if (window) return window;
  }
  // The servers' own APIs sit beside the OpenAI-style one, not under its /v1.
  const root = base.replace(/\/v1$/, "");
  const model = encodeURIComponent(config.model);
  const [llamaCpp, ollama, lmStudio] = await Promise.all([
    getJson(config, `${root}/props?model=${model}`).then(llamaCppWindow),
    getJson(config, `${root}/api/ps`).then((body) => ollamaWindow(body, config.model)),
    getJson(config, `${root}/api/v1/models`).then((body) => lmStudioWindow(body, config.model)),
  ]);
  return llamaCpp ?? ollama ?? lmStudio;
}

/** A JSON answer to a GET of `url`, or undefined when there is none in time. */
async function getJson(config: ServerQuery, url: string): Promise<unknown> {
  try {
    const response = await (config.fetch ?? fetch)(url, {
      headers: config.apiKey ? { Authorization: `Bearer ${config.apiKey}` } : {},
      signal: AbortSignal.timeout(REQUEST_MS.modelProbe),
    });
    return response.ok ? ((await response.json()) as unknown) : undefined;
  } catch {
    return undefined;
  }
}

/** The list's entry for `model`, or its only entry: a one-model server (llama.cpp) serves it whatever it is named. */
function listedModel(body: unknown, model: string): Record<string, unknown> | undefined {
  const data = field(body, "data");
  if (!Array.isArray(data)) return undefined;
  const entries = data.filter(isRecord);
  return entries.find((entry) => entry.id === model) ?? (entries.length === 1 ? entries[0] : undefined);
}

/** llama.cpp: each slot's context, which is what one request gets. */
function llamaCppWindow(body: unknown): number | undefined {
  return tokens(field(field(body, "default_generation_settings"), "n_ctx"));
}

/** Ollama: the context the running model was loaded with (a model not loaded yet reports none). */
function ollamaWindow(body: unknown, model: string): number | undefined {
  const models = field(body, "models");
  if (!Array.isArray(models)) return undefined;
  // Ollama names a model with its tag; `name` means `name:latest`.
  const names = model.includes(":") ? [model] : [model, `${model}:latest`];
  const running = models
    .filter(isRecord)
    .find((entry) => names.includes(entry.name as string) || names.includes(entry.model as string));
  return tokens(running?.context_length);
}

/** LM Studio: the context the loaded instance of the model runs with (a model not loaded reports none). */
function lmStudioWindow(body: unknown, model: string): number | undefined {
  const models = field(body, "models");
  if (!Array.isArray(models)) return undefined;
  for (const entry of models.filter(isRecord)) {
    const instances = Array.isArray(entry.loaded_instances) ? entry.loaded_instances.filter(isRecord) : [];
    // A request names a loaded instance by its id, or the model by its key.
    const instance =
      instances.find((item) => item.id === model) ?? (entry.key === model ? instances[0] : undefined);
    const window = tokens(field(instance?.config, "context_length"));
    if (window) return window;
  }
  return undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function field(value: unknown, name: string): unknown {
  return isRecord(value) ? value[name] : undefined;
}

/** A token count: a positive whole number, else undefined. */
function tokens(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : undefined;
}
