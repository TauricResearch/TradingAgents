// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The questions the agent asked, as question steps over a FormUI: each its choices, numbered, and a last row
 * to type an answer of one's own, one after another. The reply is one line per question, `header: answer`,
 * sent as the next question; Esc on the first question leaves them unanswered, on a later one goes back to
 * it, with the answer given kept.
 */
import { type EventEnvelope, message, type Question } from "../contracts/index.js";
import { BACK, type FormUI } from "./form/form-ui.js";
import type { QuestionAnswer } from "./form/question-state.js";

/** The reply to `questions`, or undefined when they were left unanswered. */
export async function answerQuestions(
  ui: FormUI,
  questions: readonly Question[],
): Promise<string | undefined> {
  // Each answer as given (a choice's place, or the words typed), so going back opens a question on it.
  const given: (QuestionAnswer | undefined)[] = [];
  for (let at = 0; at < questions.length; ) {
    const question = questions[at] as Question;
    const before = given[at];
    const answer = await ui.question({
      title: question.question,
      header: question.header,
      ...(questions.length > 1 ? { position: `${at + 1}/${questions.length}` } : {}),
      options: question.options.map((option, index) => ({
        id: String(index),
        label: option.label,
        ...(option.note ? { note: option.note } : {}),
      })),
      own: message("ask.own"),
      ...(before && "choice" in before ? { start: before.choice } : {}),
      ...(before && "own" in before ? { initial: before.own } : {}),
      // Esc on the first question leaves them unanswered and the input comes back; on a later one, back.
      esc: at === 0 ? "close" : "back",
    });
    // Esc on the first question leaves them unanswered; on a later one, it goes back a question.
    if (answer === BACK) {
      if (at === 0) return undefined;
      at--;
      continue;
    }
    given[at] = answer;
    at++;
  }
  return questions
    .map((question, index) => {
      const answer = given[index] as QuestionAnswer;
      const words = "own" in answer ? answer.own : (question.options[answer.choice]?.label ?? "");
      return `${question.header}: ${words}`;
    })
    .join("\n");
}

/**
 * The questions a session's last turn ended with, still unanswered: only when that turn completed (a
 * stopped or failed one is not in the conversation), and none once a later question was asked.
 */
export function pendingQuestions(events: readonly EventEnvelope[] = []): Question[] | undefined {
  let completed = false;
  for (const { event, parent } of events.toReversed()) {
    if (event.type === "turn.started" || event.type === "turn.cancelled" || event.type === "turn.failed")
      return undefined;
    if (event.type === "turn.completed") completed = true;
    if (event.type === "question.asked" && !parent) return completed ? event.questions : undefined;
  }
  return undefined;
}
