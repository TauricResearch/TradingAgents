// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Models at a hosted API, reached with the user's own key: each through its AI SDK package, wrapped by
 * the shared client. Nothing is sampled (vendors fix sampling for their reasoning models); how much a
 * model reasons is a level, the configured one when it thinks and its least when a request is made
 * without thinking.
 */
import { createAnthropic } from "@ai-sdk/anthropic";
import { createDeepSeek } from "@ai-sdk/deepseek";
import { createGoogleGenerativeAI } from "@ai-sdk/google";
import { createOpenAI } from "@ai-sdk/openai";
import { createOpenAICompatible } from "@ai-sdk/openai-compatible";
import { createOpenRouter } from "@openrouter/ai-sdk-provider";
import type { LanguageModel } from "ai";
import {
  type HostedProvider,
  type ModelClient,
  type ModelRequest,
  message,
  type ReasoningLevel,
  type Replay,
} from "../contracts/index.js";
import { AiSdkModelClient, type ProviderClassifier, type StepOptions } from "./ai-sdk.js";
import { fitReasoning, leastReasoning, modelInfo } from "./catalog.js";

/** OpenAI's API: the only address an OpenAI key or a ChatGPT plan's tokens are sent to. */
export const OPENAI_API_BASE = "https://api.openai.com/v1";

/** Tauric's model API, OpenAI-compatible: reached with the same key as its data. */
const TAURIC_MODELS_BASE = "https://api.tauric.ai/v1";

type HostedRoute = {
  provider: HostedProvider;
  model: string;
  apiKey: string;
  reasoning?: ReasoningLevel;
};

/** Who a hosted model's replay data may be sent back to: its provider and model. */
export function hostedReplayKey(route: Pick<HostedRoute, "provider" | "model">): string {
  return `${route.provider} ${route.model}`;
}

/** OpenAI's option for a request's cache key: requests with the same key are routed to the same cache. */
export function promptCacheKey(request: ModelRequest): { promptCacheKey?: string } {
  return request.cacheKey ? { promptCacheKey: request.cacheKey } : {};
}

/** The level a step reasons at: the setting when it thinks, the model's least when it does not. */
export function stepReasoning(
  route: { provider: string; model: string; reasoning?: ReasoningLevel },
  thinking: boolean | undefined,
): ReasoningLevel {
  if (thinking === false) return leastReasoning(route.provider, route.model);
  return fitReasoning(route.provider, route.model, route.reasoning ?? "provider-default");
}

/** A refused key, said with where to make a new one. */
const keyRefused = (provider: string, url: string, said: string) => ({
  kind: "auth" as const,
  message: message("model.keyRefused", { provider, url, said }),
  retryable: false,
});
/** An account out of credit: not worth retrying until credit is added. */
const noCredit = (provider: string, said: string) => ({
  kind: "rate_limited" as const,
  message: message("model.noCredit", { provider, said }),
  retryable: false,
});

/** OpenAI's own failures: a refused key, an account out of credit (not worth retrying), a busy one. */
const openaiFailure: ProviderClassifier = ({ status, code, type, message: said }) => {
  if (status === 401) return keyRefused("OpenAI", "https://platform.openai.com/api-keys", said);
  if (code === "insufficient_quota" || type === "insufficient_quota") return noCredit("OpenAI", said);
  return undefined;
};

/** Anthropic's own failures: a refused key, a balance too low (an invalid request), a refused request. */
const anthropicFailure: ProviderClassifier = ({ status, type, message: said }) => {
  if (status === 401 || type === "authentication_error")
    return keyRefused("Anthropic", "https://console.anthropic.com/settings/keys", said);
  if (/credit balance is too low/i.test(said)) return noCredit("Anthropic", said);
  return undefined;
};

/** Google's own failures: a key it does not accept arrives as an invalid request. */
const googleFailure: ProviderClassifier = ({ status, message: said }) => {
  if (status === 401 || /API key not valid|API_KEY_INVALID/i.test(said))
    return keyRefused("Google", "https://aistudio.google.com/apikey", said);
  return undefined;
};

/**
 * OpenRouter's own failures: a refused key, no credit left (402; a spending limit reached for the
 * moment is worth waiting for), a request its moderation refused (403).
 */
const openrouterFailure: ProviderClassifier = ({ status, body, message: said }) => {
  if (status === 401) return keyRefused("OpenRouter", "https://openrouter.ai/settings/keys", said);
  if (status === 402 && body?.includes("in_flight_budget"))
    return { kind: "rate_limited", message: said, retryable: true };
  if (status === 402) return noCredit("OpenRouter", said);
  if (status === 403) return { kind: "provider", message: said, retryable: false };
  return undefined;
};

/** Tauric's own failures: a refused key, the day's AI credits spent (not worth retrying before they reset). */
const tauricFailure: ProviderClassifier = ({ status, code, body, message: said }) => {
  if (status === 401) return keyRefused("Tauric", "https://tauric.ai/settings/api-keys", said);
  if (code === "quota_exhausted") {
    const resets = resetTime(body);
    return {
      kind: "rate_limited",
      message: message("model.creditsSpent", resets ? { resets } : {}),
      retryable: false,
    };
  }
  return undefined;
};

/** When a spent pool resets, from the error's `resets_at`, as "2026-11-24 00:00 UTC". */
function resetTime(body: string | undefined): string | undefined {
  try {
    const at = (JSON.parse(body ?? "") as { error?: { resets_at?: unknown } }).error?.resets_at;
    const ms = typeof at === "string" ? Date.parse(at) : Number.NaN;
    return Number.isNaN(ms) ? undefined : `${new Date(ms).toISOString().slice(0, 16).replace("T", " ")} UTC`;
  } catch {
    return undefined;
  }
}

/** DeepSeek's own failures: a refused key, a balance that ran out (402, not worth retrying). */
const deepseekFailure: ProviderClassifier = ({ status, message: said }) => {
  if (status === 401) return keyRefused("DeepSeek", "https://platform.deepseek.com/api_keys", said);
  if (status === 402) return noCredit("DeepSeek", said);
  return undefined;
};

/** LLMTR's own failures: a refused or expired key. */
const llmtrFailure: ProviderClassifier = ({ status, message: said }) => {
  if (status === 401) return keyRefused("LLMTR", "https://llmtr.com/dashboard", said);
  return undefined;
};

/** OpenRouter's reasoning details carry the reasoning itself: a finished turn keeps the rest. */
function withoutReasoningDetails(replay: Replay): Replay | undefined {
  const { openrouter, ...rest } = replay;
  const { reasoning_details: _, ...kept } = (openrouter ?? {}) as Record<string, unknown>;
  const settled = { ...rest, ...(Object.keys(kept).length ? { openrouter: kept } : {}) } as Replay;
  return Object.keys(settled).length ? settled : undefined;
}

/**
 * What differs between the hosted providers: how the SDK model is made (its package, fixed address
 * and model method), what a step asks for, how failures read, and what of a turn's reasoning is kept.
 * The address is fixed for each: a key goes to its provider, never where a *_BASE_URL variable points.
 */
type Hosted = {
  model(route: HostedRoute, fetch: typeof globalThis.fetch | undefined): LanguageModel;
  step(route: HostedRoute): StepOptions;
  classify: ProviderClassifier;
  keepsReasoning?: "conversation";
  settleReplay?: (replay: Replay) => Replay | undefined;
};

const fetching = (fetch: typeof globalThis.fetch | undefined) => (fetch ? { fetch } : {});

const HOSTED: Record<HostedProvider, Hosted> = {
  tauric: {
    model: (route, fetch) =>
      createOpenAICompatible({
        name: "tauric",
        apiKey: route.apiKey,
        baseURL: TAURIC_MODELS_BASE,
        includeUsage: true,
        ...fetching(fetch),
      }).chatModel(route.model),
    // It takes no reasoning level (thinking is not exposed) and samples as it chooses.
    step: () => () => ({ sampling: {} }),
    classify: tauricFailure,
  },
  openai: {
    model: (route, fetch) =>
      createOpenAI({ apiKey: route.apiKey, baseURL: OPENAI_API_BASE, ...fetching(fetch) }).responses(
        route.model,
      ),
    step: (route) => (request) => ({
      sampling: {},
      // Kept by the client, sent back with each request (encrypted reasoning), never stored by OpenAI.
      // A summary of the reasoning, so a person can follow it; the reasoning itself is never sent.
      providerOptions: { openai: { store: false, reasoningSummary: "auto", ...promptCacheKey(request) } },
      reasoning: stepReasoning(route, request.sampling?.thinking),
    }),
    classify: openaiFailure,
  },
  anthropic: {
    model: (route, fetch) =>
      createAnthropic({ apiKey: route.apiKey, baseURL: "https://api.anthropic.com/v1", ...fetching(fetch) })(
        route.model,
      ),
    step: (route) => (request) => {
      const reasoning = stepReasoning(route, request.sampling?.thinking);
      // The models listed think adaptively and show nothing of it unless a summary is asked for; a step
      // that skips thinking is left to switch it off.
      const summarized = modelInfo("anthropic", route.model) !== undefined && reasoning !== "none";
      return {
        sampling: {},
        reasoning,
        ...(summarized
          ? { providerOptions: { anthropic: { thinking: { type: "adaptive", display: "summarized" } } } }
          : {}),
      };
    },
    classify: anthropicFailure,
  },
  google: {
    model: (route, fetch) =>
      createGoogleGenerativeAI({
        apiKey: route.apiKey,
        baseURL: "https://generativelanguage.googleapis.com/v1beta",
        ...fetching(fetch),
      })(route.model),
    step: (route) => (request) => {
      const reasoning = stepReasoning(route, request.sampling?.thinking);
      // A model the catalog lists is asked for its level as Google names it (the SDK's own table
      // lags); another is left to the SDK. Its thoughts are streamed only when asked for.
      const listed = modelInfo("google", route.model) !== undefined && reasoning !== "provider-default";
      return {
        sampling: {},
        providerOptions: {
          google: {
            thinkingConfig: { includeThoughts: true, ...(listed ? { thinkingLevel: reasoning } : {}) },
          },
        },
        ...(listed ? {} : { reasoning }),
      };
    },
    classify: googleFailure,
  },
  deepseek: {
    model: (route, fetch) =>
      createDeepSeek({ apiKey: route.apiKey, baseURL: "https://api.deepseek.com", ...fetching(fetch) })(
        route.model,
      ),
    step: (route) => (request) => ({
      sampling: {},
      reasoning: stepReasoning(route, request.sampling?.thinking),
    }),
    classify: deepseekFailure,
    // With tools, DeepSeek needs the reasoning of every earlier turn sent back: it is kept, in the session too.
    keepsReasoning: "conversation",
  },
  openrouter: {
    model: (route, fetch) =>
      createOpenRouter({
        apiKey: route.apiKey,
        baseURL: "https://openrouter.ai/api/v1",
        ...fetching(fetch),
      }).chat(route.model),
    step: (route) => (request) => {
      const effort = stepReasoning(route, request.sampling?.thinking);
      // It takes reasoning in its own options; a step's level is its effort.
      return {
        sampling: {},
        ...(effort === "provider-default"
          ? {}
          : { providerOptions: { openrouter: { reasoning: { effort } } } }),
      };
    },
    classify: openrouterFailure,
    settleReplay: withoutReasoningDetails,
  },
  llmtr: {
    model: (route, fetch) =>
      createOpenAICompatible({
        name: "llmtr",
        apiKey: route.apiKey,
        baseURL: "https://llmtr.com/v1",
        includeUsage: true,
        ...fetching(fetch),
      }).chatModel(route.model),
    // Thinking fields have not been verified against the live LLMTR API; sampling is left to the gateway.
    step: () => () => ({ sampling: {} }),
    classify: llmtrFailure,
  },
};

export function hostedClient(
  route: HostedRoute,
  { fetch, stallMs }: { fetch?: typeof globalThis.fetch; stallMs?: number },
): ModelClient {
  const hosted = HOSTED[route.provider];
  return new AiSdkModelClient(hosted.model(route, fetch), route.model, hosted.step(route), stallMs, {
    replayKey: hostedReplayKey(route),
    classify: hosted.classify,
    ...(hosted.keepsReasoning ? { keepsReasoning: hosted.keepsReasoning } : {}),
    ...(hosted.settleReplay ? { settleReplay: hosted.settleReplay } : {}),
  });
}
