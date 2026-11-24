// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * A ModelClient on the Vercel AI SDK. Each call is one model step: tools are declared without an
 * execute function, so the SDK returns tool calls instead of running them, and the agent loop
 * decides what happens next. No AI SDK type leaves this module.
 */

import {
  APICallError,
  type JSONValue,
  jsonSchema,
  type LanguageModel,
  type ModelMessage,
  NoOutputGeneratedError,
  Output,
  type ProviderMetadata,
  StreamProviderError,
  streamText,
  type ToolSet,
  tool,
} from "ai";
import type {
  FinishReason,
  JsonValue,
  Message,
  ModelChunk,
  ModelClient,
  ModelRequest,
  ReasoningLevel,
  Replay,
  Sampling,
  ToolSpec,
} from "../contracts/index.js";
import { message as catalog, errorText } from "../contracts/index.js";
import { CONTEXT, MODEL } from "../contracts/limits.js";

/**
 * How one provider spells a step's sampling: the settings the SDK maps natively, plus raw request
 * options for what it does not (vLLM's top_k and chat_template_kwargs, for example).
 */
export type StepOptions = (request: ModelRequest) => {
  sampling: Sampling;
  providerOptions?: Record<string, Record<string, JSONValue>>;
  /** False for a route that refuses an output cap: the loop's own caps bound the run instead. */
  sendOutputCap?: boolean;
  /** How much the model reasons on this step, which the SDK spells for each provider. */
  reasoning?: ReasoningLevel;
};

// The SDK writes its warnings to the console, over the terminal app; they are not wanted there.
(globalThis as { AI_SDK_LOG_WARNINGS?: unknown }).AI_SDK_LOG_WARNINGS = false;

const nativeSampling: StepOptions = (request) => ({ sampling: request.sampling ?? {} });

export class AiSdkModelClient implements ModelClient {
  readonly replayKey: string | undefined;
  readonly keepsReasoning: "turn" | "conversation";
  readonly settleReplay: ((replay: Replay) => Replay | undefined) | undefined;

  constructor(
    private readonly languageModel: LanguageModel,
    readonly model: string,
    private readonly stepOptions: StepOptions = nativeSampling,
    /** How long a request may send nothing before it is ended as stalled. */
    private readonly stallMs: number = MODEL.stallMs,
    identity: {
      replayKey?: string;
      keepsReasoning?: "turn" | "conversation";
      /** What of its replay data a finished turn keeps (see ModelClient). */
      settleReplay?: (replay: Replay) => Replay | undefined;
      /** The provider's own reading of a failure, first; undefined leaves it to the shared rules. */
      classify?: ProviderClassifier;
    } = {},
  ) {
    this.classifyFirst = identity.classify;
    this.replayKey = identity.replayKey;
    this.keepsReasoning = identity.keepsReasoning ?? "turn";
    this.settleReplay = identity.settleReplay;
  }

  private readonly classifyFirst: ProviderClassifier | undefined;

  async *stream(request: ModelRequest, signal?: AbortSignal): AsyncIterable<ModelChunk> {
    const { sampling, providerOptions, sendOutputCap = true, reasoning } = this.stepOptions(request);
    let ended = false;
    // A route that takes no output cap is held to it here: written characters are counted as tokens
    // (conservatively) and the request is ended at the bound, as the provider would end it.
    // Text, reasoning and tool arguments all count; a delta past the bound is cut at it.
    const bound = sendOutputCap ? undefined : request.maxOutputTokens;
    const cut = new AbortController();
    // A request that sends nothing at all for the stall time is ended; any part of its stream counts.
    const stalled = new AbortController();
    let watchdog = setTimeout(() => stalled.abort(), this.stallMs);
    const arm = () => {
      clearTimeout(watchdog);
      watchdog = setTimeout(() => stalled.abort(), this.stallMs);
    };
    const stallError: ModelChunk = {
      type: "error",
      error: {
        kind: "provider",
        message: catalog("model.stalled", { durationMs: this.stallMs }),
        retryable: true,
      },
    };
    let written = 0;
    /** What of `text` fits under the bound, and whether the bound is now reached. */
    const allowed = (text: string): { kept: string; reached: boolean } => {
      if (bound === undefined) return { kept: text, reached: false };
      const room = Math.max(0, Math.floor((bound - written) * CONTEXT.charsPerToken));
      const kept = text.slice(0, room);
      written += kept.length / CONTEXT.charsPerToken;
      return { kept, reached: text.length >= room };
    };
    // The prompt is not measured on a request ended here, so it is estimated.
    const promptTokens = Math.ceil(
      (request.system.length +
        JSON.stringify(request.messages).length +
        JSON.stringify(request.tools).length) /
        CONTEXT.charsPerToken,
    );
    /** Calls whose arguments were counted as they streamed. */
    const streamed = new Set<string>();
    const lengthFinish = (): ModelChunk => ({
      type: "finish",
      reason: "length",
      usage: { inputTokens: promptTokens, outputTokens: Math.ceil(written) },
    });
    try {
      const result = streamText({
        model: this.languageModel,
        system: request.system,
        messages: toModelMessages(request.messages),
        tools: toToolSet(request.tools),
        ...(request.toolChoice ? { toolChoice: request.toolChoice } : {}),
        maxRetries: 0, // retries belong to the agent loop, which knows the caps
        // Errors arrive as chunks; the SDK's own logging would print them, secrets and all, to the console.
        onError: () => {},
        abortSignal: AbortSignal.any([...(signal ? [signal] : []), cut.signal, stalled.signal]),
        ...(sampling.temperature !== undefined ? { temperature: sampling.temperature } : {}),
        ...(sampling.topP !== undefined ? { topP: sampling.topP } : {}),
        ...(sampling.topK !== undefined ? { topK: sampling.topK } : {}),
        ...(sampling.presencePenalty !== undefined ? { presencePenalty: sampling.presencePenalty } : {}),
        ...(sendOutputCap && request.maxOutputTokens !== undefined
          ? { maxOutputTokens: request.maxOutputTokens }
          : {}),
        ...(providerOptions ? { providerOptions: providerOptions as ProviderMetadata } : {}),
        ...(reasoning ? { reasoning } : {}),
        ...(request.responseFormat
          ? {
              output: Output.object({
                schema: jsonSchema(request.responseFormat.schema as Parameters<typeof jsonSchema>[0]),
                ...(request.responseFormat.name ? { name: request.responseFormat.name } : {}),
              }),
            }
          : {}),
      });
      for await (const part of result.fullStream) {
        // A part came: no stall while it is handed on (the reader may take its time).
        clearTimeout(watchdog);
        switch (part.type) {
          case "text-start":
          case "text-delta":
          case "text-end": {
            const { kept, reached } = allowed(part.type === "text-delta" ? part.text : "");
            const replay = replayOf(part.providerMetadata);
            // At the bound the request is ended first, so it stops even if this stream is not read on.
            if (reached) {
              ended = true;
              cut.abort();
            }
            if (kept || replay)
              yield { type: "text", text: kept, block: part.id, ...(replay ? { replay } : {}) };
            if (reached) {
              yield lengthFinish();
              return;
            }
            break;
          }
          case "reasoning-start":
          case "reasoning-delta":
          case "reasoning-end": {
            // Each block keeps its own text and metadata (a redacted block's data comes with its start).
            const { kept: text, reached } = allowed(part.type === "reasoning-delta" ? part.text : "");
            const replay = replayOf(part.providerMetadata);
            if (reached) {
              ended = true;
              cut.abort();
            }
            if (text || replay) {
              yield { type: "reasoning", text, block: part.id, ...(replay ? { replay } : {}) };
            }
            if (reached) {
              yield lengthFinish();
              return;
            }
            break;
          }
          case "tool-input-delta":
            // Arguments being written count too; a call cut off here is never run.
            streamed.add(part.id);
            if (allowed(part.delta).reached) {
              ended = true;
              cut.abort();
              yield lengthFinish();
              return;
            }
            break;
          case "tool-call": {
            // A call that arrives whole counts its arguments now; one over the bound is never run.
            if (!streamed.has(part.toolCallId) && allowed(JSON.stringify(part.input)).reached) {
              ended = true;
              cut.abort();
              yield lengthFinish();
              return;
            }
            const replay = replayOf(part.providerMetadata);
            yield {
              type: "tool-call",
              callId: part.toolCallId,
              name: part.toolName,
              args: part.input as JsonValue,
              ...(replay ? { replay } : {}),
            };
            break;
          }
          case "finish":
            ended = true;
            // The provider's stream ended without its finish: the SDK closes the step with "other" and
            // no raw reason, and a provider that saw its completion event missing says "interrupted".
            if (
              part.finishReason === "interrupted" ||
              (part.finishReason === "other" && part.rawFinishReason === undefined)
            ) {
              yield { type: "error", error: unfinished() };
              return;
            }
            yield {
              type: "finish",
              reason: finishReason(part.finishReason),
              usage: {
                inputTokens: part.totalUsage.inputTokens ?? 0,
                outputTokens: part.totalUsage.outputTokens ?? 0,
                ...(part.totalUsage.outputTokenDetails.reasoningTokens !== undefined
                  ? { reasoningTokens: part.totalUsage.outputTokenDetails.reasoningTokens }
                  : {}),
                ...(part.totalUsage.inputTokenDetails.cacheReadTokens !== undefined
                  ? { cacheReadTokens: part.totalUsage.inputTokenDetails.cacheReadTokens }
                  : {}),
                ...(part.totalUsage.inputTokenDetails.cacheWriteTokens !== undefined
                  ? { cacheWriteTokens: part.totalUsage.inputTokenDetails.cacheWriteTokens }
                  : {}),
              },
            };
            break;
          case "error":
            ended = true;
            yield { type: "error", error: classify(part.error, signal, this.classifyFirst) };
            return;
          case "abort":
            // The SDK reports any failure after the request is ended as an abort, a stall included.
            ended = true;
            if (stalled.signal.aborted && !signal?.aborted) yield stallError;
            else yield { type: "error", error: { kind: "aborted", message: "cancelled", retryable: false } };
            return;
          default:
            break; // start/end markers, tool-input streaming, sources and raw parts carry nothing we use
        }
        // Waiting for the provider again: the watchdog runs only while nothing has come.
        arm();
      }
    } catch (error) {
      if (!ended) yield { type: "error", error: classify(error, signal, this.classifyFirst) };
    } finally {
      clearTimeout(watchdog);
    }
  }
}

type ModelError = Extract<ModelChunk, { type: "error" }>["error"];

/** A failure as a provider reports it: status, its code and type, and whether the SDK would retry it. */
type ProviderFailure = {
  status?: number;
  code?: string;
  type?: string;
  /** The answer's body as it came, for what the fields above do not hold. */
  body?: string;
  message: string;
  retryable: boolean;
};
/** A provider's reading of its own failure, or undefined to leave it to the shared rules. */
export type ProviderClassifier = (failure: ProviderFailure) => ModelError | undefined;

/**
 * The status, code and type an SDK error carries: its own fields, else its body, where the error may be
 * at the top, under `error`, or in a failed response's `response.error` (a stream frame).
 */
function failureFields(
  error: APICallError | StreamProviderError,
): Omit<ProviderFailure, "message" | "retryable"> {
  const fromBody = (() => {
    const body = APICallError.isInstance(error) ? error.responseBody : undefined;
    try {
      const parsed = body ? (JSON.parse(body) as Record<string, unknown>) : undefined;
      const nested = (parsed?.response as { error?: unknown } | undefined)?.error;
      return [parsed?.error, nested, parsed].find(
        (candidate): candidate is { code?: unknown; type?: unknown } =>
          typeof candidate === "object" && candidate !== null && ("code" in candidate || "type" in candidate),
      );
    } catch {
      return undefined;
    }
  })();
  const own = StreamProviderError.isInstance(error)
    ? (error as unknown as { code?: unknown; type?: unknown })
    : {};
  const code = own.code !== undefined ? String(own.code) : fromBody?.code;
  const type = typeof own.type === "string" && own.type !== "error" ? own.type : fromBody?.type;
  const body = APICallError.isInstance(error) ? error.responseBody : undefined;
  return {
    ...(error.statusCode !== undefined ? { status: error.statusCode } : {}),
    ...(body !== undefined ? { body } : {}),
    ...(typeof code === "string" ? { code } : {}),
    ...(typeof type === "string" ? { type } : {}),
  };
}

/** A stream that ended without the provider's finish: the answer may be cut short. */
function unfinished(): ModelError {
  return { kind: "provider", message: catalog("model.streamUnfinished"), retryable: true };
}

function toToolSet(tools: ToolSpec[]): ToolSet {
  return Object.fromEntries(
    tools.map((spec) => [
      spec.name,
      tool({ description: spec.description, inputSchema: jsonSchema(spec.inputSchema) }),
    ]),
  );
}

function toModelMessages(messages: Message[]): ModelMessage[] {
  return messages.map(toModelMessage);
}

function toModelMessage(message: Message): ModelMessage {
  switch (message.role) {
    case "user":
      return { role: "user", content: message.text };
    case "assistant":
      return {
        role: "assistant",
        content: message.parts.map((part) => {
          const providerOptions = part.replay ? { providerOptions: part.replay } : {};
          switch (part.type) {
            case "tool-call":
              return {
                type: "tool-call" as const,
                toolCallId: part.callId,
                toolName: part.name,
                input: part.args,
                ...providerOptions,
              };
            case "reasoning":
              return { type: "reasoning" as const, text: part.text, ...providerOptions };
            default:
              return { type: "text" as const, text: part.text, ...providerOptions };
          }
        }),
      };
    case "tool":
      return {
        role: "tool",
        content: message.results.map((result) => ({
          type: "tool-result" as const,
          toolCallId: result.callId,
          toolName: result.name,
          output: result.isError
            ? { type: "error-text" as const, value: result.output }
            : { type: "text" as const, value: result.output },
        })),
      };
    default:
      return message satisfies never;
  }
}

function finishReason(reason: string): FinishReason {
  switch (reason) {
    case "stop":
    case "tool-calls":
    case "length":
    case "content-filter":
    case "error":
      return reason;
    default:
      return "other";
  }
}

/** How servers word a request longer than the model's context window. */
const OVERFLOW =
  /context[_ ]length|context window|maximum context|prompt is too long|request too long|too many tokens|maximum.*tokens/i;

function classify(error: unknown, signal?: AbortSignal, first?: ProviderClassifier): ModelError {
  const message = errorText(error);
  if (signal?.aborted || (error instanceof Error && error.name === "AbortError")) {
    return { kind: "aborted", message: "cancelled", retryable: false };
  }
  // The SDK's word for a stream that closed before the provider sent anything or its finish, and a
  // connection that dropped while the reply came (however the SDK wrapped it): worth asking again.
  if (NoOutputGeneratedError.isInstance(error) || dropped(error)) return unfinished();
  // A failure that says how it should be reported (a sign-in that must be redone, say), however wrapped.
  const reported = failureOf(error);
  if (reported) return { ...reported, message };
  // An HTTP failure and an error the server sends inside a 200 event stream classify alike: the provider's
  // own reading first.
  if (APICallError.isInstance(error) || StreamProviderError.isInstance(error)) {
    const own = first?.({ ...failureFields(error), message, retryable: error.isRetryable });
    if (own) return own;
    if (error.statusCode === 401 || error.statusCode === 403)
      return { kind: "auth", message, retryable: false };
    const code = StreamProviderError.isInstance(error) ? String(error.code ?? "") : "";
    // Busy, worth trying again, unless the provider said it is not (an account out of credit).
    if (error.statusCode === 429)
      return { kind: "rate_limited", message, retryable: error.isRetryable !== false };
    // A request the server refused for its length: a 400 or 413 (or an error event in the stream) that
    // says so, not any failure that mentions a context (a gateway's "context deadline exceeded").
    const refused = error.statusCode === undefined || error.statusCode === 400 || error.statusCode === 413;
    if (refused && OVERFLOW.test(`${message} ${code}`)) return { kind: "context", message, retryable: false };
    return { kind: "provider", message, retryable: error.isRetryable };
  }
  // Anything else is a failure of this process (a bug, a broken stream parser), not of the server.
  return { kind: "provider", message, retryable: false };
}

/** Network codes for a connection that closed or broke under a request. */
const DROPPED_CODES = new Set([
  "ECONNRESET",
  "EPIPE",
  "ETIMEDOUT",
  "ECONNABORTED",
  "UND_ERR_SOCKET",
  "UND_ERR_CLOSED",
]);

/** Whether an error or one of its causes is the connection dropping (fetch's "terminated", a reset socket). */
function dropped(error: unknown): boolean {
  for (
    let cause = error, depth = 0;
    cause && depth < 5;
    cause = (cause as { cause?: unknown }).cause, depth++
  ) {
    const { name, message, code } = cause as { name?: unknown; message?: unknown; code?: unknown };
    if (typeof code === "string" && DROPPED_CODES.has(code)) return true;
    if (name === "TypeError" && (message === "terminated" || message === "fetch failed")) return true;
  }
  return false;
}

/** The `failure` an error or one of its causes carries, if any. */
function failureOf(error: unknown): { kind: "auth" | "provider"; retryable: boolean } | undefined {
  for (
    let cause = error, depth = 0;
    cause && depth < 5;
    cause = (cause as { cause?: unknown }).cause, depth++
  ) {
    const failure = (cause as { failure?: { kind?: unknown; retryable?: unknown } }).failure;
    if (
      (failure?.kind === "auth" || failure?.kind === "provider") &&
      typeof failure.retryable === "boolean"
    ) {
      return { kind: failure.kind, retryable: failure.retryable };
    }
  }
  return undefined;
}

function replayOf(metadata: ProviderMetadata | undefined): Replay | undefined {
  // A provider's empty entry carries nothing to send back.
  const kept = Object.entries(metadata ?? {}).filter(([, data]) => data && Object.keys(data).length);
  return kept.length ? (Object.fromEntries(kept) as Replay) : undefined;
}
