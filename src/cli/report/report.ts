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
  question: string;
  /**
   * The question asked just before in plan mode, when this one was asked in plan mode too or ran its plan
   * as proposed: the answer may carry out the plan that one got, so the reader sees what it was.
   */
  earlier?: string;
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
 * The title is the answer's opening heading when it has one. `model` stands in when the turn did not say.
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
  const before = turns.at(-2);
  const parts = reportParts(last.answer);
  const [first, ...rest] = parts;
  const titled = first?.kind === "heading";
  return {
    title: titled ? textOf(first.runs) : message("report.title"),
    question: printable(last.question).trim(),
    ...(before?.plan && (last.plan || last.question === message("app.runPlan"))
      ? { earlier: printable(before.question).trim() }
      : {}),
    at: last.at,
    model: printable(last.model ?? model),
    version: printable(version),
    parts: titled ? rest : parts,
    sources: last.sources.map((source) => printable(sourceLine(source))),
  };
}

function textOf(runs: readonly Run[]): string {
  return runs
    .map((run) => run.text)
    .join("")
    .replace(/\s+/g, " ")
    .trim();
}
