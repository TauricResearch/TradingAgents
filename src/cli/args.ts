// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The command line's words: its flags, the commands and the arguments each takes, the usage text, and
 * what is wrong with a command line before anything runs.
 */
import { parseArgs } from "node:util";
import { APP_NAME, message } from "../contracts/index.js";

export const USAGE = message("cli.usage", { app: APP_NAME });

/** Exit codes besides the headless run's own: wrong usage, missing settings. */
export const EXIT_USAGE = 2;

/** The command line read into its flags and positionals. */
export type Args = ReturnType<typeof parse>;

export function parse(argv: string[]) {
  return parseArgs({
    args: argv,
    allowPositionals: true,
    options: {
      prompt: { type: "string", short: "p" },
      limit: { type: "string", multiple: true },
      json: { type: "boolean" },
      yes: { type: "boolean" },
      continue: { type: "boolean", short: "c" },
      resume: { type: "string" },
      model: { type: "string" },
      reasoning: { type: "string" },
      help: { type: "boolean", short: "h" },
      version: { type: "boolean", short: "v" },
    },
  });
}

/** The arguments each command takes after its name; a question takes none. */
const ARGUMENTS: Record<string, number> = {
  key: 1,
  sessions: 2,
  sync: 1,
  login: 2,
  logout: 1,
  update: 0,
};
/** Flags only a question (a session or -p) reads. */
const RUN_FLAGS = ["prompt", "limit", "json", "continue", "resume", "model", "reasoning"] as const;

/**
 * What is wrong with `command`, its arguments `rest` and the flags given, if anything: a flag or an
 * argument that does not apply, a command that does not exist, or an empty question.
 */
export function misuseOf(
  command: string | undefined,
  rest: string[],
  values: Args["values"],
): string | undefined {
  if (command !== undefined && Object.hasOwn(ARGUMENTS, command)) {
    const flag = RUN_FLAGS.find((name) => values[name] !== undefined);
    if (flag) return message("cli.flagNotFor", { flag, command });
    const extra = rest[ARGUMENTS[command] ?? 0];
    if (extra !== undefined) return message("cli.unexpectedArgument", { argument: extra });
    if ((command === "login" || command === "logout") && rest[0] !== "chatgpt")
      return message("cli.sayChatgpt", { app: APP_NAME, command });
    return undefined;
  }
  if (values.yes && command !== "sessions")
    return message("cli.flagNotFor", { flag: "yes", command: command ?? "a question" });
  if (values.json && values.prompt === undefined) return message("cli.jsonNeedsPrompt");
  if (values.resume !== undefined && values.continue) return message("cli.resumeOrContinue");
  if (command !== undefined) return message("cli.unknownCommand", { command });
  if (values.prompt !== undefined && !values.prompt.trim()) return message("cli.emptyQuestion");
  return undefined;
}
