// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** The question whether to sync sessions to the Tauric account, asked once in the app. */
import { message } from "../../contracts/index.js";
import { BACK, type FormUI } from "../form/form-ui.js";

/**
 * Ask whether to turn sync on: true or false, or undefined when it was left unanswered (Esc), to be asked
 * again next time. "Turn on" comes first and the list opens on it: Enter turns sync on. Ctrl+C rejects, as
 * any step.
 */
export async function askSync(ui: FormUI): Promise<boolean | undefined> {
  const answer = await ui.pick({
    title: message("sync.question"),
    subtitle: message("sync.questionSubtitle"),
    esc: "skip",
    options: [
      { id: "on", label: message("sync.turnOn") },
      { id: "off", label: message("sync.keepOff") },
    ],
  });
  return answer === BACK ? undefined : answer === "on";
}
