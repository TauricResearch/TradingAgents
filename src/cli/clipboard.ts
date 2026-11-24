// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Text to the clipboard, with no dependency: through the terminal (OSC 52, which reaches the clipboard of the
 * machine the terminal runs on, over SSH too), and through tmux's own buffer inside tmux, and through the
 * platform's tool when the session is local. The clipboard is never read.
 */
import { spawnSync } from "node:child_process";
import { APP } from "../contracts/limits.js";

/** Terminals cap what one OSC 52 may carry; past this, the text goes only another way. */
export const OSC52_MAX_BYTES = APP.clipboardTerminalBytes;

type Environment = Readonly<Record<string, string | undefined>>;

/** How a copy went: through which ways, and whether the terminal is known to drop OSC 52. */
export type Copied = {
  /** The platform's tool, or tmux's buffer, took it. */
  local: boolean;
  /** OSC 52 was written; false when the text was too long for it. */
  terminal: boolean;
  /** The terminal is one known to ignore OSC 52 (macOS Terminal, VTE terminals such as GNOME's). */
  unsupported: boolean;
};

/** The OSC 52 sequence that sets the clipboard to `text`, wrapped for tmux or screen; undefined when too long. */
export function osc52(text: string, env: Environment): string | undefined {
  const encoded = Buffer.from(text, "utf8").toString("base64");
  if (encoded.length > OSC52_MAX_BYTES) return undefined;
  const sequence = `\u001b]52;c;${encoded}\u0007`;
  // tmux passes a sequence on to the terminal outside it inside its DCS, with each ESC doubled.
  if (env.TMUX) return `\u001bPtmux;${sequence.replaceAll("\u001b", "\u001b\u001b")}\u001b\\`;
  // screen caps one DCS string: the sequence goes in pieces, each its own.
  if (env.STY || env.TERM?.startsWith("screen")) {
    const pieces = sequence.match(/[\s\S]{1,76}/g) ?? [];
    return pieces.map((piece) => `\u001bP${piece}\u001b\\`).join("");
  }
  return sequence;
}

/**
 * The tools that set the clipboard here, in order: tmux's buffer (forwarded by tmux to the terminal), then the
 * platform's own when the session is local (not over SSH). Fixed programs and arguments, run with no shell.
 */
export function clipboardTools(platform: NodeJS.Platform, env: Environment): [string, string[]][] {
  const tools: [string, string[]][] = [];
  if (env.TMUX) tools.push(["tmux", ["load-buffer", "-w", "-"]]);
  if (env.SSH_CONNECTION || env.SSH_TTY) return tools;
  if (platform === "darwin") tools.push(["pbcopy", []]);
  else if (platform === "win32") tools.push(["clip", []]);
  else if (env.WAYLAND_DISPLAY) tools.push(["wl-copy", []]);
  else if (env.DISPLAY) tools.push(["xclip", ["-selection", "clipboard"]]);
  else if (env.WSL_DISTRO_NAME) tools.push(["clip.exe", []]);
  return tools;
}

/** Whether `command args` took `text` on its input and succeeded (a missing tool is a no). */
function ran(command: string, args: string[], text: string): boolean {
  const result = spawnSync(command, args, {
    input: text,
    stdio: ["pipe", "ignore", "ignore"],
    timeout: APP.clipboardToolMs,
  });
  return result.error === undefined && result.status === 0;
}

/** Copy `text` every way that applies; `write` sends the terminal its sequence. */
export function copyText(
  text: string,
  {
    env = process.env,
    platform = process.platform,
    write,
    run = ran,
  }: {
    env?: Environment;
    platform?: NodeJS.Platform;
    write: (sequence: string) => void;
    run?: (command: string, args: string[], text: string) => boolean;
  },
): Copied {
  const sequence = osc52(text, env);
  if (sequence) write(sequence);
  let local = false;
  for (const [command, args] of clipboardTools(platform, env)) local = run(command, args, text) || local;
  return {
    local,
    terminal: sequence !== undefined,
    unsupported: env.TERM_PROGRAM === "Apple_Terminal" || env.VTE_VERSION !== undefined,
  };
}
