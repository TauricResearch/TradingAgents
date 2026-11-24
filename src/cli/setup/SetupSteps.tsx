// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The setup before the chat: each step is its own short render that owns the keys while it is up, then
 * clears itself and leaves one dim line saying what was chosen (never what a secret holds). Between steps
 * nothing holds the terminal, so a sign-in can run there.
 */
import chalk from "chalk";
import { render, useInput, usePaste, useWindowSize } from "ink";
import { useReducer, useRef } from "react";
import { message, printable } from "../../contracts/index.js";
import { Form } from "../form/Form.js";
import { fieldBuffer } from "../form/field-state.js";
import {
  type Ask,
  type Ended,
  fieldResult,
  type OpenStep,
  openStep,
  pickResult,
  questionResult,
  stepKey,
  stepPaste,
  stepView,
} from "../form/form-step.js";
import { BACK, type FormUI } from "../form/form-ui.js";
import { burstKeys } from "../line-editor.js";
import { paint, TEXT_ROLES, type Theme } from "../theme.js";
import { ThemeContext } from "../theme-context.js";

function StepApp({ ask, done }: { ask: Ask; done: (ended: Ended) => void }) {
  const { rows } = useWindowSize();
  const open = useRef<OpenStep>(openStep(ask));
  // Keys after the step ended (the rest of a burst, a paste) are not the next step's.
  const ended = useRef(false);
  const [, redraw] = useReducer((count: number) => count + 1, 0);
  usePaste((text) => {
    if (ended.current) return;
    open.current = stepPaste(open.current, text);
    redraw();
  });
  useInput((typed, pressed) => {
    for (const [input, key] of burstKeys(typed, pressed)) {
      if (ended.current) return;
      const next = stepKey(open.current, input, key);
      if ("ended" in next) {
        ended.current = true;
        return done(next.ended);
      }
      open.current = next.open;
    }
    redraw();
  });
  return <Form step={stepView(open.current)} rows={Math.max(1, rows - 1)} />;
}

/** A FormUI on this terminal: one render per step, then a dim line of what was chosen. */
export function stepsUI(
  theme: Theme,
  io: { stdin?: NodeJS.ReadStream; stdout?: NodeJS.WriteStream } = {},
): FormUI & { cancel(): void; close(): void } {
  const stdout = io.stdout ?? process.stdout;
  const stdin = io.stdin ?? process.stdin;
  // Raw from the first step to the last, so nothing typed between steps is echoed by the terminal.
  const holdRaw = () => {
    if (stdin.isTTY) stdin.setRawMode(true);
  };
  /** Drop what was typed before a step was shown; a Ctrl+C among it still cancels. */
  const drain = () => {
    for (let chunk = stdin.read(); chunk !== null; chunk = stdin.read()) {
      if (String(chunk).includes(String.fromCodePoint(3))) cancelled = true;
    }
  };
  // Set by a SIGINT from outside: the step up now ends as Ctrl+C ends it, and so would any after it.
  let cancelled = false;
  let cancelNow: (() => void) | undefined;
  const ask = (question: Ask) =>
    new Promise<Ended>((resolve) => {
      drain();
      if (cancelled) return resolve({ kind: "cancel" });
      const app = render(
        <ThemeContext.Provider value={theme}>
          <StepApp
            ask={question}
            done={(ended) => {
              cancelNow = undefined;
              app.clear();
              app.unmount();
              holdRaw();
              resolve(ended);
            }}
          />
        </ThemeContext.Provider>,
        {
          // Only ever at a terminal (both ends): drawn as it changes, also where CI is set.
          interactive: true,
          exitOnCtrlC: false,
          patchConsole: false,
          ...(io.stdin ? { stdin: io.stdin } : {}),
          stdout,
        },
      );
      cancelNow = () => {
        cancelNow = undefined;
        app.clear();
        app.unmount();
        resolve({ kind: "cancel" });
      };
    });
  const said = (line: string) => stdout.write(`${paint(chalk, TEXT_ROLES.detail, printable(line))}\n`);
  return {
    async pick(step) {
      const id = pickResult(await ask({ kind: "pick", step }));
      if (id === BACK) return BACK;
      const label = step.options.find((option) => option.id === id)?.label ?? id;
      said(message("setup.answered", { title: step.title, answer: label }));
      return id;
    },
    async field(step) {
      const buffer = fieldBuffer(step.kind, step.initial);
      // What was typed is not echoed: it is checked after, and could be anything pasted there.
      return fieldResult(await ask({ kind: "field", step, buffer }), buffer);
    },
    async question(step) {
      return questionResult(await ask({ kind: "question", step }));
    },
    cancel() {
      cancelled = true;
      cancelNow?.();
    },
    /** The setup is over: the terminal goes back to how lines are read. */
    close() {
      drain();
      if (stdin.isTTY) stdin.setRawMode(false);
    },
  };
}
