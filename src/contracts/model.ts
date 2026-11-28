// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * How the agent loop talks to a language model. One request is one model step: the loop, not the
 * model client, decides when to call tools and when to stop.
 */
import type { MODEL_ERROR_KINDS, Usage } from "./events.js";

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export type ToolSpec = {
  name: string;
  description: string;
  /** JSON Schema of the tool's arguments (an object schema). */
  inputSchema: { [key: string]: JsonValue };
};

/**
 * Opaque data a provider attaches to reasoning or a tool call and requires back on the next step
 * (thought signatures, for example). Kept as given; never read or edited.
 */
export type Replay = { [provider: string]: { [key: string]: JsonValue } };

export type ToolCall = { callId: string; name: string; args: JsonValue; replay?: Replay };

/**
 * An assistant turn as the model produced it. Reasoning is kept so it can be sent back on the next
 * step: thinking models use more tool rounds and answer worse when their earlier reasoning is dropped.
 */
export type AssistantPart =
  | { type: "text"; text: string; replay?: Replay }
  | { type: "reasoning"; text: string; replay?: Replay }
  | ({ type: "tool-call" } & ToolCall);

/**
 * A tool's result as the model reads it. `evidence`: the recorded result it shows (`e7`), which stays
 * reachable by reference after `output` is cut to a pointer to fit the context (`elided`).
 */
export type ToolOutcome = {
  callId: string;
  name: string;
  output: string;
  isError?: boolean;
  evidence?: string;
  elided?: true;
};

export type Message =
  | { role: "user"; text: string }
  | { role: "assistant"; parts: AssistantPart[] }
  | { role: "tool"; results: ToolOutcome[] };

/**
 * A message for a request it was not written for (another provider or model): without the data its
 * provider attached, to the message or its parts, and without its reasoning, which only that model may be
 * shown again.
 */
export function withoutReplay(message: Message, { keepReasoning = false } = {}): Message {
  if (message.role !== "assistant") return message;
  return {
    role: "assistant",
    parts: message.parts
      // A model that needs every turn's reasoning back keeps its text; what a provider signed goes.
      .filter((part) => keepReasoning || part.type !== "reasoning")
      .map((part): AssistantPart => {
        if (!part.replay) return part;
        const { replay: _, ...rest } = part;
        return rest;
      }),
  };
}

/** Providers reached with an API key at their own endpoint; Tauric's key also serves its data. */
export const HOSTED_PROVIDERS = [
  "tauric",
  "openai",
  "anthropic",
  "google",
  "deepseek",
  "openrouter",
  "llmtr",
] as const;
export type HostedProvider = (typeof HOSTED_PROVIDERS)[number];

/**
 * Who serves the model: a hosted API, a ChatGPT plan signed in to, or an OpenAI-compatible server. In the
 * order they are offered: Tauric first, then the hosted ones, then a server of one's own.
 */
export const PROVIDER_IDS = [
  "tauric",
  "chatgpt",
  "openai",
  "anthropic",
  "google",
  "deepseek",
  "openrouter",
  "llmtr",
  "openai-compatible",
] as const satisfies readonly (HostedProvider | "chatgpt" | "openai-compatible")[];
export type ProviderId = (typeof PROVIDER_IDS)[number];

/** How much a model reasons, least first; `provider-default` leaves it to the provider. */
export const REASONING_LEVELS = ["none", "minimal", "low", "medium", "high", "xhigh", "max"] as const;
export type ReasoningLevel = (typeof REASONING_LEVELS)[number] | "provider-default";

/** Sampling for one mode; a value left out is the server's choice. */
export type SamplingSettings = {
  temperature?: number;
  topP?: number;
  topK?: number;
  presencePenalty?: number;
};

/**
 * A server's address as a key and replay data are bound to it: origin and path, without a query, a
 * fragment or a trailing slash.
 */
export function endpointOf(baseURL: string): string {
  try {
    const url = new URL(baseURL);
    return `${url.origin}${url.pathname.replace(/\/+$/, "")}`;
  } catch {
    return baseURL;
  }
}

/** A model as a session remembers it: no key and no address, which are resolved when it runs. */
export type RouteName = { provider: ProviderId; model: string; reasoning?: ReasoningLevel };

/** The model a run uses and how to reach it, as the settings resolved it. */
export type ModelRoute =
  | {
      provider: "chatgpt";
      model: string;
      /** How much it reasons when it thinks; the provider's default when unset. */
      reasoning?: ReasoningLevel;
      /** The context window to use, when set: else the plan's report, else a fallback. */
      contextWindow?: number;
    }
  | {
      provider: HostedProvider;
      model: string;
      apiKey: string;
      reasoning?: ReasoningLevel;
      contextWindow?: number;
    }
  | {
      provider: "openai-compatible";
      /** The model as the server names it. */
      model: string;
      baseURL: string;
      apiKey?: string;
      /** How the server is told to think: vLLM-style chat template switch, or not at all. */
      thinking: "chat-template" | "none";
      /** Model-card sampling for each mode. */
      sampling: { thinking: SamplingSettings; plain: SamplingSettings };
      contextWindow?: number;
    };

/** Sampling settings, spelled by each provider's client for its API. */
export type Sampling = SamplingSettings & {
  /** Whether a model that can think out loud should do so for this step. */
  thinking?: boolean;
};

export type ModelRequest = {
  system: string;
  messages: Message[];
  tools: ToolSpec[];
  sampling?: Sampling;
  maxOutputTokens?: number;
  /**
   * Whether the model may call the tools: "none" for a final answer, which keeps the tools declared so
   * the request stays the one its earlier reasoning was written for.
   */
  toolChoice?: "auto" | "none";
  /** A reply that must be one JSON value fitting `schema` (structured output), where the provider can hold it to one. */
  responseFormat?: { schema: { [key: string]: JsonValue }; name?: string };
  /**
   * Names the conversation the request continues: requests that share a key share their prefix, so a
   * provider that routes by it serves the prefix from its cache.
   */
  cacheKey?: string;
};

export type FinishReason = "stop" | "tool-calls" | "length" | "content-filter" | "error" | "other";

export type ModelChunk =
  /** Text; `block` and `replay` as for reasoning. */
  | { type: "text"; text: string; block?: string; replay?: Replay }
  /**
   * Reasoning text. `block` names the reasoning block it belongs to, when the provider separates them;
   * a chunk may carry only `replay`, which belongs to its block (or to the reasoning streamed so far).
   */
  | { type: "reasoning"; text: string; block?: string; replay?: Replay }
  | ({ type: "tool-call" } & ToolCall)
  | { type: "finish"; reason: FinishReason; usage: Usage }
  | {
      type: "error";
      error: {
        kind: (typeof MODEL_ERROR_KINDS)[number];
        message: string;
        /** Whether the same request may succeed if sent again; unknown failures are not retried. */
        retryable: boolean;
      };
    };

export interface ModelClient {
  /** The model's id as the provider names it, for events and cost. */
  readonly model: string;
  /**
   * Who may be sent this client's replay data back: the provider, its endpoint and the model. Replay
   * recorded under another key (another provider, server or model) is dropped before it is sent, and
   * a client without a key has none of it sent back once the turn is over.
   */
  readonly replayKey?: string | undefined;
  /**
   * Whether a finished turn's reasoning stays in the conversation ("conversation", which a provider
   * that requires earlier turns' reasoning back needs) or ends with the turn ("turn", the default).
   */
  readonly keepsReasoning?: "turn" | "conversation";
  /**
   * What of the data it attached to a part or a step a finished turn keeps, when some of it carries
   * reasoning (and so goes with the reasoning); all of it when unset.
   */
  readonly settleReplay?: ((replay: Replay) => Replay | undefined) | undefined;
  /** Stream one step. Always ends with exactly one `finish` or one `error` chunk. */
  stream(request: ModelRequest, signal?: AbortSignal): AsyncIterable<ModelChunk>;
}
