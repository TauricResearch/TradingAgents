// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * One agent run: the loop that turns a brief into an answer through model steps and tool calls.
 * The main agent and every sub-agent use it with different specs. It emits bare events; the engine wraps
 * them in envelopes, owns the session and reports how the run ended.
 *
 * Caps end the work, not the answer: when one is reached the loop stops what is running and asks
 * for one final step without tools, bounded by its own output limit and grace period. The token
 * cap counts the usage the model reports, so it is approximate (a failed attempt reports none).
 */

import type {
  AssistantPart,
  Cap,
  Clock,
  Event,
  FinishReason,
  Message,
  ModelChunk,
  ModelClient,
  Replay,
  Sampling,
  ToolCall,
  ToolOutcome,
  Usage,
} from "../contracts/index.js";
import { addUsage, type ErrorKind, message, NOTICE } from "../contracts/index.js";
import { CALLS, CONTEXT, MODEL } from "../contracts/limits.js";
import type { EvidenceScope } from "../tools/evidence-store.js";
import type { ToolContext, ToolRegistry } from "../tools/index.js";
import { elideOldest, fitToWindow, type Measured, requestChars } from "./budget.js";
import { WRAP_UP } from "./prompts.js";
import { abortableSleep, underPolicy } from "./recovery.js";

export type Caps = {
  /** Model steps that may call tools; the final answer step comes on top. */
  steps: number;
  /** Input and output tokens of this run, as the model reports them; none unless set. */
  tokens?: number;
  /** Tokens of the whole turn (`spentTokens` counts them); none unless set. */
  turnTokens?: number;
  /** Wall time of the whole run: it ends by then, the final answer included; none unless set. */
  timeMs?: number;
  /**
   * Of `timeMs`, the time kept for the final answer: gathering stops when only this much is left.
   * The smaller of the grace period and a quarter of the time unless set.
   */
  reserveMs?: number;
};

export type AgentSpec = {
  name: string;
  system: string;
  tools: readonly string[];
  caps: Caps;
  sampling?: Sampling;
  /**
   * Sampling for a final answer a time limit forced: without thinking, so the time left goes to text.
   * Unset when the model cannot be told to skip thinking.
   */
  hurriedSampling?: Sampling;
  maxOutputTokens?: number;
  /** Output the final answer step may write once a cap is reached. */
  finalOutputTokens?: number;
  /** The model's context window in tokens; requests are kept within it. Unbounded when unset. */
  contextWindow?: number;
  /** The most the model takes in, when less than its window allows besides the output. */
  inputLimit?: number;
};

type AgentDeps = {
  client: ModelClient;
  registry: ToolRegistry;
  emit: (event: Event) => void;
  signal: AbortSignal;
  now?: () => number;
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
  /** The most a time limit keeps for the final answer; 120 s unless set. */
  finalGraceMs?: number;
  /** The whole turn's tokens so far, counted against `caps.turnTokens`. */
  spentTokens?: () => number;
  /** Where the calls of a step record their results and read earlier ones; nothing is recorded unless set. */
  evidence?: (step: number, signal: AbortSignal) => EvidenceScope;
  /** The run's clock, for the tools. */
  clock?: Clock;
  /** Sent with each of the run's requests, so the provider can serve the repeated prefix from its cache. */
  cacheKey?: string;
};

export type AgentOutcome = {
  status: "completed" | "capped" | "cancelled" | "failed";
  /** The final step's text. */
  answer: string;
  usage: Usage;
  /** The run's conversation, reasoning and replay data included, for resuming it. */
  messages: Message[];
  cap?: Cap;
  /** How the model finished the final step; unset when the step ended without finishing (at the wall). */
  finish?: FinishReason;
  error?: { kind: ErrorKind; message: string };
};

type StepError = Extract<ModelChunk, { type: "error" }>["error"];
type Step = {
  parts: AssistantPart[];
  calls: ToolCall[];
  text: string;
  finish?: FinishReason;
  usage?: Usage;
  error?: StepError;
  /** What attempts set aside before this one used: counted, but not a measure of this request. */
  setAside?: Usage;
};

/**
 * The cache key of an agent's runs in a session: the main agent's is the session's own, as its
 * conversation grows turn by turn; each sub-agent's system prompt and tools are the same each time, and
 * differ from every other agent's, so each sub-agent has its own.
 */
export function cacheKeyOf(session: string, subAgent?: string): string {
  return subAgent ? `${session}:${subAgent}` : session;
}

/** Run `spec` on `brief`, after `history` (earlier turns of the same conversation, as returned before). */
export async function runAgent(
  spec: AgentSpec,
  brief: string,
  deps: AgentDeps,
  history: readonly Message[] = [],
): Promise<AgentOutcome> {
  const now = deps.now ?? Date.now;
  const sleep = deps.sleep ?? abortableSleep;
  const started = now();
  const messages: Message[] = [...history, { role: "user", text: brief }];
  const usage: Usage = { inputTokens: 0, outputTokens: 0 };
  let cap: Cap | undefined;
  const end = (
    status: AgentOutcome["status"],
    answer: string,
    error?: { kind: ErrorKind; message: string },
    finish?: FinishReason,
  ): AgentOutcome => ({
    status,
    answer,
    usage,
    messages,
    ...(cap ? { cap } : {}),
    ...(finish ? { finish } : {}),
    ...(error ? { error: { kind: error.kind, message: error.message } } : {}),
  });

  // A time limit is a wall: gathering stops when only the final answer's reserve is left, and the
  // answer is written in that reserve, ending at the wall. With no time limit there is no deadline.
  const { timeMs } = spec.caps;
  const reserve =
    timeMs === undefined
      ? 0
      : Math.floor(spec.caps.reserveMs ?? Math.min(deps.finalGraceMs ?? MODEL.finalGraceMs, timeMs / 4));
  const deadline = new AbortController();
  const timer =
    timeMs === undefined
      ? undefined
      : setTimeout(() => deadline.abort(), Math.max(0, timeMs - reserve - (now() - started)));
  let work = AbortSignal.any([deps.signal, deadline.signal]);
  /** The wall itself, once the final answer runs under it. */
  let wall: AbortSignal | undefined;
  const reachCap = (reached: Cap) => {
    cap = reached;
    clearTimeout(timer);
    const toWall = timeMs === undefined ? undefined : Math.max(0, Math.floor(timeMs - (now() - started)));
    wall = toWall === undefined ? undefined : AbortSignal.timeout(toWall);
    work = wall === undefined ? deps.signal : AbortSignal.any([deps.signal, wall]);
    deps.emit({
      type: "notice",
      level: "warn",
      code: `cap_${reached}`,
      text: message("run.cap", { cap: reached }),
    });
  };
  const timedOut = () => !cap && deadline.signal.aborted && !deps.signal.aborted;
  // The last request the model measured, and whether a context error has already been retried.
  let measured: Measured | undefined;
  let window = spec.contextWindow;
  let contextRetried = false;
  // A model that needs every turn's reasoning back keeps it when a result is set aside.
  const keeping = { keepReasoning: deps.client.keepsReasoning === "conversation" };
  let elisionNoted = false;

  try {
    for (let step = 0; ; step++) {
      if (deps.signal.aborted) return end("cancelled", "");
      const reached = cap
        ? undefined
        : capReached(
            spec.caps,
            step,
            usage.inputTokens + usage.outputTokens,
            deps.spentTokens?.() ?? 0,
            now() - started,
          );
      if (reached) reachCap(reached);

      const final = cap !== undefined;
      if (window !== undefined) {
        const tools = deps.registry.specs(spec.tools);
        const output = outputLimit(spec, final, window) ?? MODEL.defaultOutputTokens;
        // The window holds the request and its output; a model may take in less than that leaves.
        const bound = spec.inputLimit !== undefined ? Math.min(window, spec.inputLimit + output) : window;
        const elided = fitToWindow(bound, spec.system, messages, tools, output, measured, keeping);
        if (elided === undefined) {
          return end("failed", "", {
            kind: "context",
            message: message("run.tooMuchContext"),
          });
        }
        if (elided && !elisionNoted) {
          elisionNoted = true;
          deps.emit({
            type: "notice",
            level: "info",
            code: NOTICE.contextElided,
            text: message("run.olderResultsSetAside"),
          });
        }
      }
      // The wrap-up instruction is for this request only; the saved conversation does not keep it.
      const request = final ? [...messages, { role: "user" as const, text: WRAP_UP }] : messages;
      const chars = requestChars(spec.system, request, deps.registry.specs(spec.tools));
      const limit = outputLimit(spec, final, window);
      // A final answer a time limit forced is written without thinking, where the model allows it.
      const hurried = final && cap === "time" ? spec.hurriedSampling : undefined;
      const stepSpec = hurried ? { ...spec, sampling: hurried } : spec;
      const result = await streamStep(stepSpec, request, final, limit, work, deps, sleep, {
        compact: window !== undefined,
        compacted: contextRetried,
        // Twice the output stays within the final answer's limit (the model's own) and a quarter of the window.
        ceiling: Math.min(
          spec.finalOutputTokens ?? MODEL.finalOutputTokens,
          window === undefined ? Number.POSITIVE_INFINITY : Math.floor(window / 4),
        ),
      });
      const stepUsage = { inputTokens: 0, outputTokens: 0 };
      addUsage(stepUsage, result.setAside);
      addUsage(stepUsage, result.usage);
      addUsage(usage, stepUsage);
      if (result.usage?.inputTokens) measured = { inputTokens: result.usage.inputTokens, chars };
      if (result.error) {
        if (deps.signal.aborted) return end("cancelled", "");
        // The estimate was short of the provider's count: set a result aside and aim lower, once. With
        // nothing left to set aside, the same request would fail again.
        if (result.compact && window !== undefined) {
          contextRetried = true;
          if (elideOldest(messages, keeping) > 0) {
            window = Math.floor(window * CONTEXT.retryWindowShare);
            measured = undefined;
            step--;
            continue;
          }
        }
        if (timedOut()) {
          reachCap("time");
          continue;
        }
        if (final && result.error.kind === "aborted" && wall?.aborted) {
          // The answer ran to the wall: it ends there, with what was written.
          // With nothing written, the person is told the limit was too short, not left with silence.
          deps.emit(
            result.text.trim()
              ? {
                  type: "notice",
                  level: "warn",
                  code: NOTICE.answerCut,
                  text: message("run.answerCutAtLimit"),
                }
              : {
                  type: "notice",
                  level: "warn",
                  code: NOTICE.answerEmpty,
                  // A model that cannot be asked to skip thinking may answer in time once it can be.
                  text: message(spec.hurriedSampling ? "run.timeTooShort" : "run.timeTooShortThinking"),
                },
          );
          if (result.text) messages.push({ role: "assistant", parts: [{ type: "text", text: result.text }] });
          return end("capped", answerOf(messages.slice(history.length), deps.registry));
        }
        // Ended by something other than the person or a wall: a failure, not a cancellation.
        if (final && result.error.kind === "aborted") {
          return end("failed", "", { kind: "provider", message: message("run.stepError") });
        }
        if (result.error.kind === "aborted") return end("cancelled", "");
        return end("failed", "", result.error);
      }
      // Every finished step is accounted for, whatever it finished with.
      deps.emit({
        type: "model.step.completed",
        finish: result.finish ?? "other",
        usage: result.usage ?? { inputTokens: 0, outputTokens: 0 },
        ...(result.setAside ? { setAside: result.setAside } : {}),
      });
      if (result.finish === "content-filter") {
        return end("failed", "", { kind: "content_filter", message: message("run.declined") });
      }
      if (result.finish === "error") {
        return end("failed", "", { kind: "provider", message: message("run.stepError") });
      }

      if (result.calls.length === 0 || final) {
        // The final step could not call tools; calls it still made were not run, so they are not kept.
        messages.push({
          role: "assistant",
          parts: result.parts.filter((part) => part.type !== "tool-call"),
        });
        if (result.finish === "length") {
          deps.emit({
            type: "notice",
            level: "warn",
            code: NOTICE.answerCut,
            text: message("run.answerCut"),
          });
        }
        return end(
          final ? "capped" : "completed",
          answerOf(messages.slice(history.length), deps.registry),
          undefined,
          result.finish ?? "other",
        );
      }

      messages.push({
        role: "assistant",
        parts: result.parts,
      });
      const { results, ends } = await runCalls(result.calls, new Set(spec.tools), work, deps, step);
      messages.push({ role: "tool", results });
      if (deps.signal.aborted) return end("cancelled", "");
      // A call that hands the conversation to the person ends the run with its closing message.
      if (ends.length) {
        messages.push({ role: "assistant", parts: [{ type: "text", text: ends.join("\n\n") }] });
        return end("completed", answerOf(messages.slice(history.length), deps.registry), undefined, "stop");
      }
      if (timedOut()) reachCap("time");
    }
  } finally {
    clearTimeout(timer);
  }
}

/**
 * The run's answer: what it wrote after its last tool call, as the prompt says; text beside a call is
 * progress. A run that wrote nothing after it (its report beside a bookkeeping call, such as a decision
 * recorded) answers with what it wrote after its last research call (data, compute or an agent), in order.
 */
function answerOf(messages: readonly Message[], registry: Pick<ToolRegistry, "kindOf">): string {
  const calls = (research: boolean) => (message: Message) =>
    message.role === "assistant" &&
    message.parts.some(
      (part) => part.type === "tool-call" && (!research || registry.kindOf(part.name) !== "control"),
    );
  const textAfter = (index: number) =>
    messages
      .slice(index + 1)
      .flatMap((message) => (message.role === "assistant" ? message.parts : []))
      .flatMap((part) => (part.type === "text" && part.text.trim() ? [part.text.trim()] : []))
      .join("\n\n");
  return textAfter(messages.findLastIndex(calls(false))) || textAfter(messages.findLastIndex(calls(true)));
}

/**
 * The output a step may write: the spec's limit, at most the final step's own on a final step, and
 * at most a quarter of the context window when there is one.
 */
function outputLimit(spec: AgentSpec, final: boolean, window: number | undefined): number | undefined {
  const finalTokens = spec.finalOutputTokens ?? MODEL.finalOutputTokens;
  let limit = final ? Math.min(spec.maxOutputTokens ?? finalTokens, finalTokens) : spec.maxOutputTokens;
  // A step may write at most a quarter of the window, so the conversation keeps the rest.
  if (window !== undefined) limit = Math.min(limit ?? MODEL.defaultOutputTokens, Math.floor(window / 4));
  return limit;
}

function capReached(
  caps: Caps,
  step: number,
  runTokens: number,
  turnTokens: number,
  elapsedMs: number,
): Cap | undefined {
  if (step >= caps.steps) return "steps";
  if (caps.tokens !== undefined && runTokens >= caps.tokens) return "tokens";
  if (caps.turnTokens !== undefined && turnTokens >= caps.turnTokens) return "tokens";
  if (caps.timeMs !== undefined && elapsedMs >= caps.timeMs) return "time";
  return undefined;
}

/**
 * One model step under the recovery policy: tried again after a pause when the failure may pass (a
 * stream cut mid-reply included: what it wrote is set aside, and the notice says so), asked once more
 * when it came back blank (with twice the output, up to `ceiling`, when thinking took all of it). A
 * context that did not fit comes back with `compact` for the caller, which can make room. The tokens of
 * attempts set aside count in the step's usage.
 */
async function streamStep(
  spec: AgentSpec,
  messages: Message[],
  final: boolean,
  maxOutputTokens: number | undefined,
  signal: AbortSignal,
  deps: AgentDeps,
  sleep: NonNullable<AgentDeps["sleep"]>,
  allowed: { compact: boolean; compacted: boolean; ceiling: number | undefined },
): Promise<Step & { compact?: true }> {
  const { last, setAside, compact, cancelled } = await underPolicy(
    (limit) => streamOnce(spec, messages, final, limit, signal, deps),
    (step) => ({ ...step, calls: step.calls.length }),
    {
      compact: allowed.compact,
      compacted: allowed.compacted,
      ...(maxOutputTokens !== undefined ? { outputTokens: maxOutputTokens } : {}),
      ...(allowed.ceiling !== undefined ? { outputCeiling: allowed.ceiling } : {}),
    },
    signal,
    sleep,
    (step, retry) =>
      deps.emit({
        type: "notice",
        level: "warn",
        code: NOTICE.modelRetry,
        text: message("run.retrying", { reason: step.error?.message ?? "" }),
        retry,
      }),
  );
  return {
    ...last,
    ...(setAside ? { setAside } : {}),
    ...(compact ? { compact } : {}),
    ...(cancelled ? { error: { kind: "aborted", message: "cancelled", retryable: false } } : {}),
  };
}

async function streamOnce(
  spec: AgentSpec,
  messages: Message[],
  final: boolean,
  maxOutputTokens: number | undefined,
  signal: AbortSignal,
  deps: AgentDeps,
): Promise<Step> {
  const step: Step = { parts: [], calls: [], text: "" };
  const request = {
    system: spec.system,
    messages,
    // A final answer keeps the tools declared and may not call them: the request stays the one the
    // run's earlier reasoning was written for.
    tools: deps.registry.specs(spec.tools),
    ...(final ? { toolChoice: "none" as const } : {}),
    ...(spec.sampling ? { sampling: spec.sampling } : {}),
    ...(maxOutputTokens !== undefined ? { maxOutputTokens } : {}),
    ...(deps.cacheKey ? { cacheKey: deps.cacheKey } : {}),
  };
  // The text or reasoning part being written, and each provider block's part: a block's later chunks
  // (its signature at the end, say) join its own part even after another block came between.
  type Written = Extract<AssistantPart, { type: "text" | "reasoning" }>;
  let open: Written | undefined;
  const blocks = new Map<string, Written>();
  for await (const chunk of deps.client.stream(request, signal)) {
    switch (chunk.type) {
      case "text":
      case "reasoning": {
        const key = chunk.block === undefined ? undefined : `${chunk.type} ${chunk.block}`;
        const found = key === undefined ? open : blocks.get(key);
        // A chunk without a block belongs to the part being written, if it is of its kind.
        let part: Written;
        if (found && found.type === chunk.type) part = found;
        else {
          part = { type: chunk.type, text: "" };
          step.parts.push(part);
          if (key !== undefined) blocks.set(key, part);
        }
        open = part;
        part.text += chunk.text;
        if (chunk.replay) part.replay = mergeReplay(part.replay, chunk.replay);
        if (chunk.type === "text") step.text += chunk.text;
        if (chunk.text) {
          deps.emit(
            chunk.type === "text"
              ? { type: "model.text.delta", text: chunk.text }
              : { type: "model.reasoning.delta", text: chunk.text },
          );
        }
        break;
      }
      case "tool-call": {
        open = undefined;
        const { type: _, ...call } = chunk;
        step.calls.push(call);
        step.parts.push(chunk);
        break;
      }
      case "finish":
        step.finish = chunk.reason;
        step.usage = chunk.usage;
        break;
      case "error":
        step.error = chunk.error;
        break;
    }
  }
  return step;
}

/**
 * Run a step's calls and return their results in the order asked: all parallel-safe calls a few at
 * a time, otherwise one after another. Calls beyond the per-step limit are answered without running.
 */
async function runCalls(
  calls: ToolCall[],
  allowed: ReadonlySet<string>,
  signal: AbortSignal,
  deps: AgentDeps,
  step: number,
): Promise<{ results: ToolOutcome[]; ends: string[] }> {
  const evidence = deps.evidence?.(step, signal);
  const context: ToolContext = {
    signal,
    ...(evidence ? { evidence } : {}),
    ...(deps.clock ? { clock: deps.clock } : {}),
  };
  for (const call of calls) {
    const kind = deps.registry.kindOf(call.name);
    deps.emit({
      type: "tool.called",
      call: call.callId,
      name: call.name,
      args: call.args,
      label: deps.registry.label(call.name, call.args, evidence, deps.clock?.() ?? new Date()),
      ...(kind ? { kind } : {}),
    });
  }
  // The closing messages of calls that end the run, by call.
  const ends: (string | undefined)[] = new Array(calls.length);
  const runOne = async (call: ToolCall, index: number): Promise<ToolOutcome> => {
    const outcome =
      index < CALLS.perStep
        ? await deps.registry.execute(call, allowed, context)
        : {
            output: `Not run: one step may call at most ${CALLS.perStep} tools. Ask again for what you still need.`,
            summary: message("tool.notRun"),
            chars: 0,
            truncated: false,
            failure: "failed" as const,
          };
    deps.emit(
      outcome.failure
        ? {
            type: "tool.failed",
            call: call.callId,
            error: {
              kind: outcome.failure,
              message: outcome.summary,
              ...(outcome.code ? { code: outcome.code } : {}),
            },
          }
        : {
            type: "tool.completed",
            call: call.callId,
            summary: outcome.truncated ? `${outcome.summary} (cut)` : outcome.summary,
            chars: outcome.chars,
            ...(outcome.source ? { source: outcome.source } : {}),
            ...(outcome.evidence ? { evidence: outcome.evidence } : {}),
            ...(outcome.asOf ? { asOf: outcome.asOf } : {}),
            ...(outcome.preview ? { preview: outcome.preview } : {}),
          },
    );
    if (outcome.ends && !outcome.failure) ends[index] = outcome.ends;
    return {
      callId: call.callId,
      name: call.name,
      output: outcome.output,
      ...(outcome.failure ? { isError: true } : {}),
      ...(outcome.evidence ? { evidence: outcome.evidence } : {}),
    };
  };
  // In the order asked: a call that must run alone does, and each run of parallel-safe calls between
  // such calls runs at once.
  const outcomes: ToolOutcome[] = new Array(calls.length);
  for (let start = 0; start < calls.length; ) {
    let end = start + 1;
    if (deps.registry.parallelSafe([calls[start] as ToolCall])) {
      while (end < calls.length && deps.registry.parallelSafe([calls[end] as ToolCall])) end++;
    }
    let next = start;
    const worker = async () => {
      while (next < end) {
        const index = next++;
        outcomes[index] = await runOne(calls[index] as ToolCall, index);
      }
    };
    await Promise.all(Array.from({ length: Math.min(CALLS.atOnce, end - start) }, worker));
    start = end;
  }
  return { results: outcomes, ends: ends.filter((text) => text !== undefined) };
}

/** Replay data a block sent in pieces: each provider's fields together, the later piece's value winning. */
function mergeReplay(earlier: Replay | undefined, later: Replay): Replay {
  const merged: Replay = { ...earlier };
  for (const [provider, data] of Object.entries(later)) merged[provider] = { ...merged[provider], ...data };
  return merged;
}
