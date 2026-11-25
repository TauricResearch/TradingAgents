// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The report an answer makes: the active session's last completed turn as the engine ended it (its question,
 * final answer with citations numbered as its sources are, the model the session ran on, and when).
 * `/export pdf` sets it as a PDF (pdf.ts).
 */
import { message, printable, sourceLine } from "../../contracts/index.js";
import type { Answered, Block } from "../transcript-state.js";
import { type Part, type Run, reportParts } from "./layout.js";

export type Report = {
  title: string;
  /** For an answer to a plan, or one that ran it as proposed: the question the planning started from. */
  question: string;
  /** What the person added while planning, in the order said: the replies in plan mode after the question. */
  added: string[];
  /** When the answer was written, as an ISO time. */
  at: string;
  model: string;
  version: string;
  parts: Part[];
  /** Each cited source as one line: "[1] price_history AAPL, 1y (Tauric, as of 2026-11-19)". */
  sources: string[];
};

/**
 * The last completed turn of `session` in `done` as a report, or undefined when it has none with an answer.
 * The question of a plan is the one the planning started from, not the reply that ran it. The title is the answer's opening heading when it has one. `model` stands in when the turn did not say.
 */
export function lastReport(
  done: readonly Block[],
  { session, model, version }: { session: string; model: string; version: string },
): Report | undefined {
  const turns = done.flatMap((block): Answered[] =>
    block.kind === "turnEnd" && block.answered.session === session ? [block.answered] : [],
  );
  const last = turns.at(-1);
  if (!last?.answer.trim()) return undefined;
  const [asked, ...added] = planning(turns);
  const parts = reportParts(last.answer);
  const [first, ...rest] = parts;
  const titled = first?.kind === "heading";
  return {
    title: titled ? textOf(first.runs) : message("report.title"),
    question: printable((asked ?? last).question).trim(),
    added: added.map((turn) => printable(turn.question).trim()).filter(Boolean),
    at: last.at,
    model: printable(last.model ?? model),
    version: printable(version),
    parts: titled ? rest : parts,
    sources: last.sources.map((source) => printable(sourceLine(source))),
  };
}

/**
 * The turns a plan was made in, when the last of `turns` answered in plan mode or ran the plan as proposed:
 * the plan-mode turns up to it (the run itself left out), in order. Otherwise none.
 */
function planning(turns: readonly Answered[]): Answered[] {
  const last = turns.at(-1);
  const ran = !last?.plan && last?.question === message("app.runPlan");
  if (!last?.plan && !ran) return [];
  const end = ran ? turns.length - 1 : turns.length;
  let start = end;
  while (start > 0 && turns[start - 1]?.plan) start--;
  return turns.slice(start, end);
}

function textOf(runs: readonly Run[]): string {
  return runs
    .map((run) => run.text)
    .join("")
    .replace(/\s+/g, " ")
    .trim();
}
