// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Reading a secret: from a terminal without echoing it, or from a pipe. Never from the command line,
 * where it would land in shell history and the process list.
 */

/** The person pressed Ctrl+C while a secret was being typed. */
export class InputCancelledError extends Error {
  override readonly name = "InputCancelledError";
}

/**
 * One line typed at a terminal, not shown. However the read ends (Enter, Ctrl+C, the input closing
 * or failing), the terminal's mode is restored and the listeners removed, once.
 */
export function readHidden(
  prompt: string,
  input: NodeJS.ReadStream,
  output: NodeJS.WriteStream,
  signal?: AbortSignal,
): Promise<string> {
  return new Promise((resolve, reject) => {
    let value = "";
    let done = false;
    // Where an escape sequence (a key such as an arrow) has got to; its bytes are never part of the value.
    let sequence: "none" | "esc" | "csi" = "none";
    const wasRaw = input.isRaw;
    const finish = (error?: Error) => {
      if (done) return;
      done = true;
      signal?.removeEventListener("abort", onAbort);
      input.off("data", onData);
      input.off("end", onEnd);
      input.off("close", onEnd);
      input.off("error", onError);
      input.setRawMode(wasRaw);
      input.pause();
      output.write("\n");
      if (error) reject(error);
      else resolve(value);
    };
    const onData = (chunk: string) => {
      for (const character of chunk) {
        if (sequence === "esc") {
          sequence = character === "[" || character === "O" ? "csi" : "none";
          if (sequence !== "none") continue;
        } else if (sequence === "csi") {
          // CSI and SS3 (which some terminals send with parameters): parameters and intermediates run to
          // a final byte from @ to ~; any other character ends the sequence and is read as typed.
          if (character >= " " && character <= "~") {
            if (character >= "@") sequence = "none";
            continue;
          }
          sequence = "none";
        }
        if (character === "\r" || character === "\n") return finish();
        if (character === "\u0003") return finish(new InputCancelledError("cancelled"));
        if (character === "\u0004") return finish(new Error("the input closed"));
        if (character === "\u001b") sequence = "esc";
        else if (character === "\u009b") sequence = "csi";
        else if (character === "\u007f" || character === "\b") value = value.slice(0, -1);
        else if (character >= " " && !(character >= "\u0080" && character <= "\u009f")) value += character;
      }
    };
    const onEnd = () => finish(new Error("the input closed"));
    const onAbort = () => finish(new InputCancelledError("closed"));
    const onError = (error: Error) => finish(error);
    output.write(prompt);
    input.setRawMode(true);
    input.setEncoding("utf8");
    input.on("data", onData);
    input.on("end", onEnd);
    input.on("close", onEnd);
    input.on("error", onError);
    input.resume();
    if (signal?.aborted) onAbort();
    else signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * Lines typed at a terminal, not shown, one after another until `close()` (a sign-in that finished in the
 * browser no longer waits for a pasted address); Ctrl+C ends them and calls `cancelled`. The terminal's
 * mode is restored whichever way they end.
 */
export function hiddenLines(
  prompt: string,
  input: NodeJS.ReadStream,
  output: NodeJS.WriteStream,
  cancelled: () => void,
): { lines: AsyncIterable<string>; close(): void } {
  const stop = new AbortController();
  async function* lines() {
    for (;;) {
      try {
        yield await readHidden(prompt, input, output, stop.signal);
      } catch (error) {
        if (!stop.signal.aborted && error instanceof InputCancelledError) cancelled();
        return;
      }
    }
  }
  return { lines: lines(), close: () => stop.abort() };
}

/** Everything piped in. */
export async function readPiped(input: NodeJS.ReadStream): Promise<string> {
  let text = "";
  input.setEncoding("utf8");
  for await (const chunk of input) text += chunk;
  return text;
}
