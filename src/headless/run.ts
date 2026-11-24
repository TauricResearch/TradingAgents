// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Headless: one question, answered without a terminal UI. `jsonl` writes every event as one JSON
 * line, for programs and agents; `answer` writes only the final answer.
 */

import { message, NOTICE, numberCitations, printable, type Source, sourceLine } from "../contracts/index.js";
import type { AskOptions, Turn, TurnOutcome } from "../engine/index.js";

type HeadlessFormat = "jsonl" | "answer";

/**
 * Where lines go: a Node writable stream or anything shaped like one, which calls `done` once each
 * write is handled. A write fails by throwing, by passing an error to `done`, or by an `error` event,
 * as a closed pipe does.
 */
export type Output = {
  write(text: string, done?: (error?: Error | null) => void): unknown;
  on?(event: "error", listener: (error: Error) => void): unknown;
  off?(event: "error", listener: (error: Error) => void): unknown;
};

/** Exit codes: answered, failed (including output that could not be written), answered at a cap, cancelled. */
export const EXIT = { completed: 0, failed: 1, capped: 3, cancelled: 130 } as const;

export async function runHeadless(
  engine: { ask(question: string, options?: AskOptions): Turn },
  question: string,
  { out, err, format, signal }: { out: Output; err: Output; format: HeadlessFormat; signal?: AbortSignal },
): Promise<{ code: number; outcome: TurnOutcome }> {
  // Asked in auto mode: a plan would wait for an approval nobody is there to give.
  const turn = engine.ask(question, signal ? { signal } : {});
  let broken = false;
  // Nobody is reading any more: stop the work rather than answer into the void.
  const fail = () => {
    if (broken) return;
    broken = true;
    turn.cancel();
  };
  const pending: Promise<void>[] = [];
  // A failed write to `out` means nobody reads the answer; one to `err` is let go (notes are best effort).
  // Only JSON lines carry text as sent (JSON escapes control characters); the rest reaches a terminal.
  const write = (target: Output, text: string) => {
    if (broken) return;
    const failed = target === out ? fail : () => {};
    pending.push(
      new Promise<void>((resolve) => {
        try {
          target.write(format === "jsonl" && target === out ? text : printable(text), (error) => {
            if (error) failed();
            resolve();
          });
        } catch {
          failed();
          resolve();
        }
      }),
    );
  };
  const ignore = () => {};
  // The main agent's own notice that its time ran out before any answer was written (a sub-agent's has a parent).
  let unwritten: string | undefined;
  // The results the answer cites, numbered: the answer is written with their numbers and listed after it.
  let sources: Source[] = [];
  out.on?.("error", fail);
  err.on?.("error", ignore);
  try {
    for await (const envelope of turn.events) {
      const { event } = envelope;
      if (event.type === "notice" && event.code === NOTICE.answerEmpty && !envelope.parent)
        unwritten = event.text;
      if (event.type === "turn.completed") sources = event.sources ?? [];
      if (format === "jsonl") write(out, `${JSON.stringify(envelope)}\n`);
      // A person reading only the answer is told the main agent's warnings and the sign-up nudge (whoever
      // met it); a cap is said once at the end, as is an answer the time left unwritten.
      else if (event.type === "notice") {
        const warning =
          !envelope.parent &&
          event.level !== "info" &&
          !event.code.startsWith("cap_") &&
          event.code !== NOTICE.answerEmpty;
        if (warning || event.code === NOTICE.capabilityUnavailable) write(err, `${event.text}\n`);
      } else if (event.type === "compaction.failed")
        write(err, `${message("run.summaryFailed", { reason: event.error.message })}\n`);
    }
    const outcome = await turn.outcome;
    if (format === "answer") {
      // Models often open with blank lines; the answer itself starts at its first text.
      const answer = numberCitations(outcome.answer, sources).trim();
      if (answer) {
        const listed = sources.length
          ? `\n\n${message("answer.sources")}\n${sources.map(sourceLine).join("\n")}`
          : "";
        write(out, `${answer}${listed}\n`);
      }
      if (outcome.status === "failed") write(err, `${outcome.error?.message ?? message("run.failed")}\n`);
      if (outcome.status === "capped") {
        const said = unwritten ?? message("run.cap", { cap: outcome.cap ?? "steps" });
        write(err, `${said}\n`);
      }
      // What the question took, for anyone who wants to set a limit.
      if (outcome.status === "completed" || outcome.status === "capped") {
        const line = message("app.usagePlain", {
          durationMs: outcome.durationMs,
          inputTokens: outcome.usage.inputTokens,
          outputTokens: outcome.usage.outputTokens,
        });
        write(err, `${line}\n`);
      }
    }
    await Promise.all(pending);
    return { code: broken ? EXIT.failed : EXIT[outcome.status], outcome };
  } finally {
    out.off?.("error", fail);
    err.off?.("error", ignore);
  }
}
