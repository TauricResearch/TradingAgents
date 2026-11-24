// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Model calls on a ChatGPT plan: OpenAI's Responses API at api.openai.com with the signed-in plan's
 * token. The plan's route takes no output cap, temperature or top-p and keeps nothing server-side, so
 * those are never sent (the agent loop's own caps still bound a run), and system text goes as the
 * developer's instructions. The token is added only for OpenAI's own origin, and a refused token is
 * renewed once and the request tried again.
 */
import { createOpenAI } from "@ai-sdk/openai";
import { type ModelClient, message, type ReasoningLevel } from "../contracts/index.js";
import { AiSdkModelClient, type ProviderClassifier } from "./ai-sdk.js";
import type { ChatGPTAuth } from "./chatgpt-auth.js";
import { OPENAI_API_BASE, promptCacheKey, stepReasoning } from "./hosted.js";
import { scrubbingSecrets } from "./scrub.js";

/** Who a ChatGPT plan client's replay data may be sent back to. */
export function chatgptReplayKey(model: string): string {
  return `chatgpt ${OPENAI_API_BASE} ${model}`;
}

/** The plan's own failure: its usage limit is reached until the plan says otherwise, not worth retrying now. */
const chatgptFailure: ProviderClassifier = ({ code, body, message: said }) =>
  /usage_limit/.test(`${said} ${body ?? ""} ${code ?? ""}`)
    ? { kind: "rate_limited", message: message("model.usageLimit"), retryable: false }
    : undefined;

export function chatgptClient({
  model,
  auth,
  fetch: fetchImpl = fetch,
  stallMs,
  reasoning,
}: {
  model: string;
  auth: ChatGPTAuth;
  /** How much it reasons when it thinks; the provider's default when unset. */
  reasoning?: ReasoningLevel;
  fetch?: typeof globalThis.fetch;
  /** How long a request may send nothing before it is ended as stalled. */
  stallMs?: number;
}): ModelClient {
  const origin = new URL(OPENAI_API_BASE).origin;
  // Every token sent, so an error that repeats one is scrubbed of it.
  const sent = new Set<string>();
  // A wrapper lacks the `preconnect` that Bun's fetch type adds, so it is asserted to the fetch type.
  const signedFetch = (async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input));
    if (url.origin !== origin) throw new Error(`refusing to send the ChatGPT token to ${url.origin}`);
    const send = async (token: string) => {
      sent.add(token);
      const headers = new Headers(init?.headers);
      headers.set("Authorization", `Bearer ${token}`);
      return fetchImpl(input, { ...init, headers, redirect: "error" });
    };
    const token = await auth.accessToken();
    const response = await send(token);
    if (response.status !== 401) return response;
    // The refused answer is discarded, so its connection is freed; a failure to discard stops nothing.
    await response.body?.cancel().catch(() => {});
    // Renewed once, unless another request already replaced the refused token.
    return send(await auth.accessToken({ rejected: token }));
  }) as typeof globalThis.fetch;
  // The SDK requires a key; the real token is set per request above.
  const provider = createOpenAI({
    baseURL: OPENAI_API_BASE,
    apiKey: "signed-in-with-chatgpt",
    fetch: signedFetch,
  });
  const client = new AiSdkModelClient(
    provider.responses(model),
    model,
    (request) => ({
      sampling: {},
      providerOptions: {
        // The plan serves reasoning models only, whatever their names: each is asked for a summary of its
        // reasoning, so a person can follow it; the reasoning itself is never sent.
        openai: {
          store: false,
          systemMessageMode: "developer",
          forceReasoning: true,
          reasoningSummary: "auto",
          ...promptCacheKey(request),
        },
      },
      // A request asked without thinking reasons as little as the model can.
      reasoning: stepReasoning(
        { provider: "chatgpt", model, ...(reasoning ? { reasoning } : {}) },
        request.sampling?.thinking,
      ),
      sendOutputCap: false,
    }),
    stallMs,
    { replayKey: chatgptReplayKey(model), classify: chatgptFailure },
  );
  return scrubbingSecrets(client, () => [...sent]);
}
