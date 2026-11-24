// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The question at start when a newer release is known: update now, skip, or skip until a newer release.
 * Asked only in a terminal session, and only for a copy that can be updated from here (see `updateWay`).
 * Updating runs `selfUpdate` or the package manager's command, says how it went, and on success asks the
 * person to start again; otherwise the session opens on this version.
 */
import { spawn } from "node:child_process";
import { APP_NAME, message } from "../contracts/index.js";
import type { FormUI } from "./form/form-ui.js";
import { type UpdateResult, type UpdateWay, updateReport } from "./self-update.js";

type UpdatePromptDeps = {
  ui: FormUI;
  latest: string;
  current: string;
  way: UpdateWay;
  /** Lets the terminal go before an update runs (the package manager prints to it). */
  close(): void;
  selfUpdate(): Promise<UpdateResult>;
  /** Runs a command on this terminal and gives its exit code. */
  run(file: string, args: string[]): Promise<number>;
  skip(version: string): Promise<void>;
  out(text: string): void;
  err(text: string): void;
};

/** "exit" once updated (the new version runs at the next start); "continue" to open the session. */
export async function offerUpdate(deps: UpdatePromptDeps): Promise<"exit" | "continue"> {
  const { latest, current, way } = deps;
  const command = way.kind === "npm" ? way.command : `${APP_NAME} update`;
  const answer = await deps.ui.pick({
    title: message("update.promptTitle", { latest, current }),
    esc: "skip",
    options: [
      { id: "now", label: message("update.now"), detail: message("update.nowDetail", { command }) },
      { id: "skip", label: message("update.skip"), detail: message("update.skipDetail") },
      {
        id: "version",
        label: message("update.skipVersion"),
        detail: message("update.skipVersionDetail", { latest }),
      },
    ],
  });
  if (answer === "version") await deps.skip(latest);
  // Skip, or Esc (BACK): the session opens on this version.
  if (answer !== "now") return "continue";
  deps.close();
  if (way.kind === "npm") {
    const [file, ...args] = way.command.split(" ");
    const code = await deps.run(file as string, args).catch(() => -1);
    if (code !== 0) {
      deps.err(`${message("update.commandFailed", { command: way.command, code })}\n`);
      return "continue";
    }
    deps.out(`${message("update.restart", { app: APP_NAME })}\n`);
    return "exit";
  }
  const report = await updateReport(deps.selfUpdate);
  if (report.failed) deps.err(`${report.text}\n`);
  else if (!report.updated) deps.out(`${report.text}\n`);
  else deps.out(`${report.text} ${message("update.restart", { app: APP_NAME })}\n`);
  return report.updated ? "exit" : "continue";
}

/** Run `file` with `args` on this terminal (its output shown as it comes) and give its exit code. */
export function runOnTerminal(file: string, args: string[]): Promise<number> {
  return new Promise((resolve, reject) => {
    const child = spawn(file, args, { stdio: "inherit" });
    child.once("error", reject);
    child.once("exit", (code, signal) => resolve(code ?? (signal ? 128 : 1)));
  });
}
