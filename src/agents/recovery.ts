// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * What to do after a model call: one policy for every call the engine makes (agent steps, history
 * summaries, lessons). A failure that may pass (a stream cut mid-reply included) is tried again after a
 * pause, what arrived of it set aside; a context that did not fit is made smaller once, where the caller
 * can; a reply that came back blank is asked for once more, with twice the output when thinking took all
 * of it.
 */
import { setTimeout as delay } from "node:timers/promises";
import {
  addUsage,
  type FinishReason,
  type ModelChunk,
  type ModelClient,
  type ModelRequest,
  type Usage,
} from "../contracts/index.js";
import { MODEL } from "../contracts/limits.js";

export type Attempt = {
  error?: Extract<ModelChunk, { type: "error" }>["error"];
  finish?: FinishReason;
  text: string;
  calls: number;
};

/** What the call has been through so far. */
type Tried = { backoffs: number; regenerated: boolean; compacted: boolean };

/**
 * What the caller can do: make its context smaller, and the output it asked for and may ask for at
 * most. `unseen`: the reply is read whole, not shown as it streams, so a cut one can be asked for again.
 */
type Allowed = { compact: boolean; unseen?: boolean; outputTokens?: number; outputCeiling?: number };

type Recovery =
  | { action: "done" }
  | { action: "backoff"; delayMs: number }
  | { action: "compact" }
  | { action: "regenerate"; maxOutputTokens?: number }
  | { action: "fatal" };

export function recover(attempt: Attempt, tried: Tried, allowed: Allowed): Recovery {
  const { error } = attempt;
  if (error) {
    if (error.kind === "aborted") return { action: "fatal" };
    const delayMs = MODEL.retryMs[tried.backoffs];
    if (error.retryable && delayMs !== undefined) return { action: "backoff", delayMs };
    if (error.kind === "context" && allowed.compact && !tried.compacted) return { action: "compact" };
    return { action: "fatal" };
  }
  const blank = !attempt.text.trim() && attempt.calls === 0;
  const cut = attempt.finish === "length" && attempt.calls === 0 && (blank || allowed.unseen === true);
  if ((!blank && !cut) || tried.regenerated) return { action: "done" };
  if (cut) {
    const { outputTokens, outputCeiling } = allowed;
    if (outputTokens === undefined || outputCeiling === undefined || outputTokens >= outputCeiling) {
      return { action: "done" };
    }
    return { action: "regenerate", maxOutputTokens: Math.min(outputTokens * 2, outputCeiling) };
  }
  if (attempt.finish === "stop" || attempt.finish === "other") return { action: "regenerate" };
  return { action: "done" };
}

/** A pause that ends early, rejecting, when `signal` aborts. */
export function abortableSleep(ms: number, signal: AbortSignal): Promise<void> {
  return delay(ms, undefined, { signal });
}

/**
 * One model call under the policy: `attempt` makes it with an output limit, `view` reads it for the
 * policy, and `onRetry` hears of each pause (which retry it is, of how many). What comes back is the
 * last attempt, the tokens of the attempts set aside before it, and whether the caller is to make room
 * (`compact`) or the pause was cancelled (`cancelled`).
 */
export async function underPolicy<A extends { usage?: Usage }>(
  attempt: (maxOutputTokens: number | undefined) => Promise<A>,
  view: (attempt: A) => Attempt,
  { outputTokens, outputCeiling, compact, compacted = false, unseen }: Allowed & { compacted?: boolean },
  signal: AbortSignal,
  sleep: (ms: number, signal: AbortSignal) => Promise<void>,
  onRetry: (attempt: A, retry: { attempt: number; of: number }) => void = () => {},
): Promise<{ last: A; setAside?: Usage; compact?: true; cancelled?: true }> {
  const tried: Tried = { backoffs: 0, regenerated: false, compacted };
  let limit = outputTokens;
  let setAside: Usage | undefined;
  for (;;) {
    const last = await attempt(limit);
    // The attempts before this one; this one's own tokens are the caller's to count.
    const set = setAside ? { setAside } : {};
    const decision = recover(view(last), tried, {
      compact,
      ...(unseen ? { unseen } : {}),
      ...(limit !== undefined ? { outputTokens: limit } : {}),
      ...(outputCeiling !== undefined ? { outputCeiling } : {}),
    });
    if (signal.aborted || decision.action === "done" || decision.action === "fatal") return { last, ...set };
    if (decision.action === "compact") return { last, ...set, compact: true };
    setAside = { ...(setAside ?? { inputTokens: 0, outputTokens: 0 }) };
    addUsage(setAside, last.usage);
    if (decision.action === "regenerate") {
      tried.regenerated = true;
      if (decision.maxOutputTokens !== undefined) limit = decision.maxOutputTokens;
      continue;
    }
    tried.backoffs++;
    onRetry(last, { attempt: tried.backoffs, of: MODEL.retryMs.length });
    try {
      await sleep(decision.delayMs, signal);
    } catch {
      return { last, ...set, cancelled: true };
    }
  }
}

/**
 * A model call whose reply is read whole rather than shown as it streams (a history summary, a
 * lesson), under the recovery policy; a cut reply is asked for again with up to twice the output.
 * Every attempt's tokens count in `usage`.
 */
export async function complete(
  client: ModelClient,
  request: ModelRequest,
  signal: AbortSignal,
  sleep: (ms: number, signal: AbortSignal) => Promise<void> = abortableSleep,
): Promise<{ text: string; finish?: FinishReason; usage: Usage; error?: Attempt["error"] }> {
  const limit = request.maxOutputTokens;
  const { last, setAside } = await underPolicy(
    async (maxOutputTokens) => {
      const attempt: Attempt & { usage: Usage } = {
        text: "",
        calls: 0,
        usage: { inputTokens: 0, outputTokens: 0 },
      };
      for await (const chunk of client.stream(
        { ...request, ...(maxOutputTokens !== undefined ? { maxOutputTokens } : {}) },
        signal,
      )) {
        if (chunk.type === "text") attempt.text += chunk.text;
        if (chunk.type === "tool-call") attempt.calls++;
        if (chunk.type === "finish") {
          attempt.finish = chunk.reason;
          addUsage(attempt.usage, chunk.usage);
        }
        if (chunk.type === "error") attempt.error = chunk.error;
      }
      return attempt;
    },
    (attempt) => attempt,
    {
      compact: false,
      unseen: true,
      ...(limit !== undefined ? { outputTokens: limit, outputCeiling: limit * 2 } : {}),
    },
    signal,
    sleep,
  );
  const usage: Usage = { inputTokens: 0, outputTokens: 0 };
  addUsage(usage, setAside);
  addUsage(usage, last.usage);
  return {
    text: last.text,
    ...(last.finish ? { finish: last.finish } : {}),
    usage,
    ...(last.error ? { error: last.error } : {}),
  };
}
