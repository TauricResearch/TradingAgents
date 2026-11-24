// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** A model client whose error messages never repeat a secret it was given (an API key, say). */
import type { ModelClient } from "../contracts/index.js";
import { KEYS } from "../contracts/limits.js";

/** `secrets` is a list, or a function giving the list as it is now (for tokens that rotate). */
export function scrubbingSecrets(
  client: ModelClient,
  secrets: readonly string[] | (() => readonly string[]),
): ModelClient {
  const current = typeof secrets === "function" ? secrets : () => secrets;
  if (typeof secrets !== "function" && !secrets.some((secret) => secret.length >= KEYS.scrubMinChars))
    return client;
  const scrub = (text: string) =>
    current()
      .filter((secret) => secret.length >= KEYS.scrubMinChars)
      .reduce((out, secret) => out.replaceAll(secret, "***"), text);
  return {
    model: client.model,
    ...(client.replayKey !== undefined ? { replayKey: client.replayKey } : {}),
    ...(client.keepsReasoning !== undefined ? { keepsReasoning: client.keepsReasoning } : {}),
    ...(client.settleReplay !== undefined ? { settleReplay: client.settleReplay } : {}),
    async *stream(request, signal) {
      for await (const chunk of client.stream(request, signal)) {
        yield chunk.type === "error"
          ? { ...chunk, error: { ...chunk.error, message: scrub(chunk.error.message) } }
          : chunk;
      }
    },
  };
}
