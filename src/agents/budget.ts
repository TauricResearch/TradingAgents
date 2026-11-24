// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Keeping a request within the model's context window. The size of the next request is estimated
 * from the last one the model measured, plus what was added since at a conservative two characters
 * a token (market data tokenizes densely: digits and tables), plus the output the step may write. When it would not fit, the oldest data
 * results are set aside, oldest first: each is cut to a pointer to its id (still reachable by the
 * evidence tool and by reference); never a sub-agent's report, a loaded skill, or the results the model
 * has not seen yet. A call keeps its result, so the
 * conversation stays valid.
 */

import { AGENT_TOOL, type Message, type ToolSpec, withoutReplay } from "../contracts/index.js";
import { CONTEXT } from "../contracts/limits.js";

export type Measured = { inputTokens: number; chars: number };

/** The characters a request sends, as a stand-in for its tokens. */
export function requestChars(
  system: string,
  messages: readonly Message[],
  tools: readonly ToolSpec[],
): number {
  return system.length + JSON.stringify(messages).length + JSON.stringify(tools).length;
}

/**
 * Tokens a request is expected to need, its output included. From a measurement, characters added
 * since count at CONTEXT.charsPerToken and characters removed since (results set aside) at
 * CONTEXT.savedCharsPerToken, so neither is understated.
 */
export function estimateTokens(chars: number, maxOutputTokens: number, last?: Measured): number {
  const change = last ? chars - last.chars : 0;
  const input = last
    ? last.inputTokens +
      (change >= 0
        ? Math.ceil(change / CONTEXT.charsPerToken)
        : -Math.floor(-change / CONTEXT.savedCharsPerToken))
    : Math.ceil(chars / CONTEXT.charsPerToken);
  return input + maxOutputTokens + CONTEXT.marginTokens;
}

const CUT = "[cut to fit the context: evidence shows it again by its id, and references to it still work]";

type Result = Extract<Message, { role: "tool" }>["results"][number];

/**
 * Whether a result may be set aside: recorded (it stays reachable by its id), not an agent's report,
 * long enough for it to save something, and not set aside already.
 */
function elidable(result: Result): boolean {
  return (
    Boolean(result.evidence) &&
    result.name !== AGENT_TOOL &&
    !result.elided &&
    result.output.length >= CONTEXT.minElidedChars
  );
}

/** What a result set aside leaves: a pointer to its id. */
function setAside(result: Result): Result {
  const head = result.output.split("\n", 1)[0] ?? "";
  return {
    ...result,
    output: `${head.startsWith(`[${result.evidence}]`) ? head : `[${result.evidence}] ${result.name}`}\n${CUT}`,
    elided: true,
  };
}

/**
 * Replace the oldest elidable result (the last tool message excepted, which the model has not seen),
 * in place. What providers attached to the assistant turns after it, and their reasoning, is dropped
 * too: it was signed over the history before it, which has changed. Returns the characters saved, 0 when
 * there is nothing left to elide.
 */
export function elideOldest(messages: Message[], { keepReasoning = false } = {}): number {
  const lastTool = messages.findLastIndex((message) => message.role === "tool");
  for (const [index, message] of messages.entries()) {
    if (message.role !== "tool" || index === lastTool) continue;
    const at = message.results.findIndex(elidable);
    if (at < 0) continue;
    const result = message.results[at] as Result;
    const kept = setAside(result);
    const note = kept.output;
    const results = [...message.results];
    results[at] = kept;
    messages[index] = { role: "tool", results };
    for (let later = index + 1; later < messages.length; later++) {
      messages[later] = withoutReplay(messages[later] as Message, { keepReasoning });
    }
    return JSON.stringify(result.output).length - JSON.stringify(note).length;
  }
  return 0;
}

/**
 * Elide results until the request fits `window` tokens. Returns how many were elided, or undefined
 * when it cannot be made to fit. The last measurement still holds after eliding (see estimateTokens).
 */
export function fitToWindow(
  window: number,
  system: string,
  messages: Message[],
  tools: readonly ToolSpec[],
  maxOutputTokens: number,
  last?: Measured,
  options: { keepReasoning?: boolean } = {},
): number | undefined {
  let elided = 0;
  while (estimateTokens(requestChars(system, messages, tools), maxOutputTokens, last) > window) {
    if (elideOldest(messages, options) === 0) return undefined;
    elided++;
  }
  return elided;
}
