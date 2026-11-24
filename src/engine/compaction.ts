// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Compaction between turns: when the conversation so far would take more than half the context
 * window, its older turns are replaced by a summary the model writes from them, and the latest turn
 * is kept as it was if it fits in a quarter. The session file keeps everything; only what the next
 * turn starts from changes.
 */

import { elideOldest } from "../agents/budget.js";
import {
  COMPACTION_INSTRUCTIONS,
  COMPACTION_SYSTEM,
  compactionPrompt,
  SUMMARY_LABEL,
} from "../agents/prompts.js";
import { complete } from "../agents/recovery.js";
import {
  type ErrorInfo,
  type Message,
  type ModelClient,
  type Sampling,
  type Usage,
  withoutReplay,
} from "../contracts/index.js";
import { CONTEXT } from "../contracts/limits.js";

const tokens = (value: unknown) => Math.ceil(JSON.stringify(value).length / CONTEXT.charsPerToken);

/** The history split into turns, each starting at a user message. */
export function turnsOf(history: readonly Message[]): Message[][] {
  const turns: Message[][] = [];
  for (const message of history) {
    if (message.role === "user" || !turns.length) turns.push([message]);
    else turns.at(-1)?.push(message);
  }
  return turns;
}

/**
 * Whether the history and the next question would take more than half of `window`, and if so which
 * turns to summarize and which to keep as they are. `measured` is the history's size as the model
 * last counted it, which is used over the estimate when known.
 */
export function compactionPlan(
  history: readonly Message[],
  question: string,
  window: number,
  measured?: number,
): { summarize: Message[]; keep: Message[] } | undefined {
  if (!history.length || (measured ?? tokens(history)) + tokens(question) <= window / 2) return undefined;
  const turns = turnsOf(history);
  const last = turns.at(-1) ?? [];
  const keepLast = turns.length > 1 && tokens(last) <= window / 4;
  return {
    summarize: (keepLast ? turns.slice(0, -1) : turns).flat(),
    keep: keepLast ? last : [],
  };
}

/** Output the summary may take in `window`: a quarter of it at most. */
function summaryTokens(window: number): number {
  return Math.min(CONTEXT.summaryTokens, Math.floor(window / 4));
}

/**
 * The conversation as text for the summary request, at most what the window leaves after the
 * instructions and the summary. To fit, the oldest data results are set aside first, then the
 * longest texts are shortened in their middle, so every turn keeps its start and end; whatever is
 * still over is cut from the middle of the whole.
 */
export function transcriptFor(messages: readonly Message[], window: number): string {
  const copy = structuredClone(messages) as Message[];
  const budget = Math.max(
    0,
    (window - summaryTokens(window) - CONTEXT.marginTokens) * CONTEXT.charsPerToken -
      COMPACTION_INSTRUCTIONS.length -
      COMPACTION_SYSTEM.length -
      CONTEXT.transcriptSlackChars,
  );
  let text = render(copy);
  while (text.length > budget && elideOldest(copy) > 0) text = render(copy);
  while (text.length > budget && shortenLongest(copy, text.length - budget)) text = render(copy);
  if (text.length <= budget) return text;
  const marker = "\n[… part of the conversation left out to fit …]\n";
  const half = Math.max(0, Math.floor((budget - marker.length) / 2));
  return `${text.slice(0, half)}${marker}${text.slice(text.length - half)}`;
}

/** Shorten the longest text of the messages by about `excess` characters (at most half of it); false if none is worth it. */
function shortenLongest(messages: Message[], excess: number): boolean {
  let longest: { get: () => string; set: (text: string) => void } | undefined;
  let size = 0;
  for (const message of messages) {
    const texts =
      message.role === "user"
        ? [{ get: () => message.text, set: (text: string) => Object.assign(message, { text }) }]
        : message.role === "tool"
          ? message.results.map((result) => ({
              get: () => result.output,
              set: (text: string) => Object.assign(result, { output: text }),
            }))
          : message.parts.flatMap((part) =>
              part.type === "text"
                ? [{ get: () => part.text, set: (text: string) => Object.assign(part, { text }) }]
                : [],
            );
    for (const text of texts) {
      if (text.get().length > size) {
        size = text.get().length;
        longest = text;
      }
    }
  }
  if (!longest || size < CONTEXT.minElidedChars) return false;
  const cut = Math.min(Math.ceil(size / 2), excess + CONTEXT.shortenSlackChars);
  const keep = size - cut;
  const value = longest.get();
  longest.set(
    `${value.slice(0, Math.ceil(keep / 2))} […] ${value.slice(value.length - Math.floor(keep / 2))}`,
  );
  return true;
}

type Line = { role: string; text?: string; tool?: string; args?: string };

/** One JSON line per message part: what each says is quoted, so no text can pose as another role. */
function render(messages: readonly Message[]): string {
  return messages
    .flatMap((message): Line[] => {
      if (message.role === "user") return [{ role: "user", text: message.text }];
      if (message.role === "tool")
        return message.results.map((r) => ({ role: "tool result", tool: r.name, text: r.output }));
      return message.parts.flatMap((part): Line[] => {
        if (part.type === "text") return [{ role: "assistant", text: part.text }];
        if (part.type !== "tool-call") return [];
        const args = JSON.stringify(part.args);
        return [
          {
            role: "assistant tool call",
            tool: part.name,
            args: args.length > CONTEXT.argumentChars ? `${args.slice(0, CONTEXT.argumentChars - 1)}…` : args,
          },
        ];
      });
    })
    .map((line) => JSON.stringify(line))
    .join("\n");
}

/**
 * Write the summary and return the history that replaces the old one, or why it could not be
 * written (the history is then left as it was). The summary opens the first kept user message; when
 * no turn is kept, it is returned as `prefix` for the next question, so user and assistant messages
 * still alternate.
 */
export async function compact(
  plan: { summarize: Message[]; keep: Message[] },
  window: number,
  client: ModelClient,
  sampling: Sampling | undefined,
  cancel: AbortSignal,
): Promise<{ history: Message[]; prefix?: string; usage: Usage } | { error: ErrorInfo; usage: Usage }> {
  const signal = AbortSignal.any([cancel, AbortSignal.timeout(CONTEXT.summaryMs)]);
  const prompt = compactionPrompt(transcriptFor(plan.summarize, window));
  const { text, finish, usage, error } = await complete(
    client,
    {
      system: COMPACTION_SYSTEM,
      messages: [{ role: "user", text: prompt }],
      tools: [],
      maxOutputTokens: summaryTokens(window),
      ...(sampling ? { sampling } : {}),
    },
    signal,
  );
  if (error) return { error: { kind: error.kind, message: error.message }, usage };
  if (finish !== "stop")
    return { error: { kind: "failed", message: `the summary was cut off (${finish ?? "other"})` }, usage };
  if (!text.trim()) return { error: { kind: "failed", message: "the summary came back empty" }, usage };
  const summary = `${SUMMARY_LABEL}\n${text.trim()}`;
  const [first, ...rest] = plan.keep;
  if (first?.role !== "user") return { history: [], prefix: summary, usage };
  // What follows the rewritten question was signed over the history as it was: its provider data goes.
  return {
    history: [
      { role: "user", text: `${summary}\n\n---\n\n${first.text}` },
      ...rest.map((message) =>
        withoutReplay(message, { keepReasoning: client.keepsReasoning === "conversation" }),
      ),
    ],
    usage,
  };
}
