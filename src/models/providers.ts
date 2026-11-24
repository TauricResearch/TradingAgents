// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The model providers: the one place that knows how each builds a client, names its replay data,
 * finds a model's context window and samples. Everything else asks the registry for a route's
 * provider.
 */
import type { ModelClient, ModelRoute, SamplingSettings } from "../contracts/index.js";
import { REQUEST_MS } from "../contracts/limits.js";
import { type CatalogProvider, modelInfo } from "./catalog.js";
import { chatgptClient, chatgptReplayKey } from "./chatgpt.js";
import { ChatGPTAuth } from "./chatgpt-auth.js";
import { hostedClient, hostedReplayKey } from "./hosted.js";
import { compatibleReplayKey, openAICompatibleClient, serverContextWindow } from "./openai-compatible.js";
import { scrubbingSecrets } from "./scrub.js";

/** What building or asking a provider may need from the setup. */
export type ProviderDeps = {
  fetch?: typeof globalThis.fetch;
  /** How long a model request may send nothing before it is ended as stalled. */
  stallMs?: number;
  /** The private file a ChatGPT sign-in is kept in. */
  chatgptAuthPath?: string;
  /**
   * Every key the settings found: kept out of what the model's client says, besides its own. The list is
   * read as it is then, so a key added to it later is kept out too.
   */
  secrets?: readonly string[];
};

type ProviderDefinition<R extends ModelRoute> = {
  client(route: R, deps: ProviderDeps): ModelClient;
  /** Who replay data written by the route's model may be sent back to: provider, endpoint and model. */
  replayKey(route: R): string;
  /** The context window the provider reports for the route's model, if it can be asked. */
  reportedWindow(route: R, deps: ProviderDeps): Promise<number | undefined>;
  windowFromPlan: boolean;
  /** Sampling for each mode, and whether a step can be asked not to think. */
  sampling(route: R): { thinking: SamplingSettings; plain: SamplingSettings; canSkipThinking: boolean };
  /** What the model takes in and writes at most, apart from its window, when known. */
  limits(route: R): { input?: number; output?: number };
};

/** A catalog model's input and output limits. */
function catalogLimits(provider: CatalogProvider, model: string): { input?: number; output?: number } {
  const info = modelInfo(provider, model);
  return { ...(info?.input ? { input: info.input } : {}), ...(info?.output ? { output: info.output } : {}) };
}

const chatgpt: ProviderDefinition<Extract<ModelRoute, { provider: "chatgpt" }>> = {
  client: (route, deps) =>
    chatgptClient({
      model: route.model,
      auth: signIn(deps),
      ...(route.reasoning ? { reasoning: route.reasoning } : {}),
      ...(deps.stallMs !== undefined ? { stallMs: deps.stallMs } : {}),
      ...(deps.fetch ? { fetch: deps.fetch } : {}),
    }),
  replayKey: (route) => chatgptReplayKey(route.model),
  // The plan lists each model's context window; without a sign-in file there is no plan to ask.
  async reportedWindow(route, deps) {
    if (!deps.chatgptAuthPath) return undefined;
    const listed = await signIn(deps)
      .models(REQUEST_MS.modelProbe)
      .catch(() => undefined);
    // What the plan reports, else what the catalog lists for the model.
    return (
      listed?.find((model) => model.id === route.model)?.contextWindow ??
      modelInfo("chatgpt", route.model)?.context
    );
  },
  windowFromPlan: true,
  // The plan's route takes no sampling; its models can be asked to reason less.
  sampling: () => ({ thinking: {}, plain: {}, canSkipThinking: true }),
  limits: (route) => catalogLimits("chatgpt", route.model),
};

const openAICompatible: ProviderDefinition<Extract<ModelRoute, { provider: "openai-compatible" }>> = {
  client: (route, deps) =>
    openAICompatibleClient({
      baseURL: route.baseURL,
      model: route.model,
      thinkingSwitch: route.thinking,
      ...(deps.stallMs !== undefined ? { stallMs: deps.stallMs } : {}),
      ...(route.apiKey ? { apiKey: route.apiKey } : {}),
      ...(deps.fetch ? { fetch: deps.fetch } : {}),
    }),
  replayKey: compatibleReplayKey,
  reportedWindow: (route, deps) =>
    serverContextWindow({
      baseURL: route.baseURL,
      model: route.model,
      ...(route.apiKey ? { apiKey: route.apiKey } : {}),
      ...(deps.fetch ? { fetch: deps.fetch } : {}),
    }),
  windowFromPlan: false,
  // A server's thinking can be switched off only through its chat template.
  sampling: (route) => ({ ...route.sampling, canSkipThinking: route.thinking === "chat-template" }),
  limits: () => ({}),
};

const hosted: ProviderDefinition<Extract<ModelRoute, { apiKey: string; provider: HostedProviderId }>> = {
  client: (route, deps) =>
    hostedClient(route, {
      ...(deps.stallMs !== undefined ? { stallMs: deps.stallMs } : {}),
      ...(deps.fetch ? { fetch: deps.fetch } : {}),
    }),
  replayKey: hostedReplayKey,
  // A hosted model's window is what the catalog lists for it.
  reportedWindow: async (route) => modelInfo(route.provider, route.model)?.context,
  windowFromPlan: false,
  // Nothing is sampled; a step without thinking reasons at the model's least.
  sampling: () => ({ thinking: {}, plain: {}, canSkipThinking: true }),
  limits: (route) => catalogLimits(route.provider, route.model),
};
type HostedProviderId = Exclude<ModelRoute["provider"], "chatgpt" | "openai-compatible">;

/** The provider serving one route, its operations bound to that route. */
type Provider = {
  client(deps: ProviderDeps): ModelClient;
  /** Who replay data written by the route's model may be sent back to: provider, endpoint and model. */
  replayKey: string;
  /** The context window the provider reports for the route's model, if it can be asked. */
  reportedWindow(deps: ProviderDeps): Promise<number | undefined>;
  /** Whether an unreported window is a plan's (else the provider's), for the notice that says so. */
  windowFromPlan: boolean;
  sampling: { thinking: SamplingSettings; plain: SamplingSettings; canSkipThinking: boolean };
  limits: { input?: number; output?: number };
};

/** The provider serving `route`. */
export function providerOf(route: ModelRoute): Provider {
  switch (route.provider) {
    case "chatgpt":
      return bound(chatgpt, route);
    case "openai-compatible":
      return bound(openAICompatible, route);
    default:
      return bound(hosted, route);
  }
}

function bound<R extends ModelRoute>(definition: ProviderDefinition<R>, route: R): Provider {
  return {
    client: (deps) => {
      const client = definition.client(route, deps);
      // The route's own key, and every key the settings know (read each time: one stored while the
      // session runs joins the list).
      const own = "apiKey" in route && route.apiKey ? [route.apiKey] : [];
      return scrubbingSecrets(client, () => [...own, ...(deps.secrets ?? [])]);
    },
    replayKey: definition.replayKey(route),
    reportedWindow: (deps) => definition.reportedWindow(route, deps),
    windowFromPlan: definition.windowFromPlan,
    sampling: definition.sampling(route),
    limits: definition.limits(route),
  };
}

function signIn(deps: ProviderDeps): ChatGPTAuth {
  if (!deps.chatgptAuthPath) throw new Error("a ChatGPT model needs the sign-in's file");
  return new ChatGPTAuth({ path: deps.chatgptAuthPath, ...(deps.fetch ? { fetch: deps.fetch } : {}) });
}
