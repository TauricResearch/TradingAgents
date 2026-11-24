// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The composition root: an engine built from resolved settings (the model endpoint, its sampling
 * per mode, the data keys). It reads no files and no environment; the CLI resolves those first.
 */

import { BUILT_IN, builtinCatalog, type Catalog, matchTools, withSkills } from "../agents/catalog.js";
import type { AgentSpec } from "../agents/index.js";
import { mainPrompt } from "../agents/prompts.js";

import {
  APP_NAME,
  type Clock,
  type ModelRoute,
  message,
  printable,
  type RouteName,
} from "../contracts/index.js";
import { DEFAULT_LIMITS, type Limits, MODEL, SYNC } from "../contracts/limits.js";
import type { Capability, DailyBars, PriceHistory } from "../data/capabilities.js";
import { DataError } from "../data/errors.js";
import { PolymarketClient } from "../data/polymarket/client.js";
import { polymarketProvider } from "../data/polymarket/provider.js";
import { CAPABILITY_LABELS, type KeyFix, type Providers, route } from "../data/router.js";
import { ROUTES } from "../data/routes.js";
import { TauricApplications } from "../data/tauric/applications.js";
import { TauricClient } from "../data/tauric/client.js";
import { tauricProvider } from "../data/tauric/provider.js";
import { yahooProvider } from "../data/yahoo/provider.js";
import { ChatGPTAuth } from "../models/chatgpt-auth.js";
import { type ProviderDeps, providerOf } from "../models/providers.js";
import { computeTools, dataTools } from "../tools/catalog.js";
import type { EvidenceStore } from "../tools/evidence-store.js";
import { evidenceTool, ToolRegistry } from "../tools/index.js";
import { Engine, type RestoredState } from "./engine.js";
import { Memory } from "./memory.js";
import type { ClosesSource } from "./settlement.js";
import type { RemoteSessions, RemoteSummary } from "./sync.js";

type EngineSettings = {
  model: ModelRoute;
  /** What a question and its agents may use; the defaults (step guards only) unless given. */
  limits?: Limits;
  tauricKey?: string;
  version: string;
  /** The clock turns are dated by (tests fix it). */
  today?: Date;
  fetch?: typeof globalThis.fetch;
  /** The data providers to use instead of this setup's own (recorded answers, say). */
  providers?: Providers;
  /** The model's context window in tokens; requests of the main agent and sub-agents are kept within it. */
  contextWindow?: number;
  /** What the model takes in and writes at most, when its catalog entry says. */
  modelLimits?: { input?: number; output?: number };
  /** The private file a ChatGPT sign-in is kept in (for the chatgpt provider). */
  chatgptAuthPath?: string;
  /** Every key the settings found, kept out of what the model's client says. */
  secrets?: readonly string[];
  /** Where notes, decisions and lessons are kept across sessions; no memory when unset. */
  dataDir?: string;
  /** The session to continue, and where it left off. */
  session?: string;
  restore?: RestoredState;
  /** The session's recorded results; the engine keeps its own in memory when unset. */
  evidence?: EvidenceStore;
  /** The agents and skills to offer; the built-in ones when unset. */
  catalog?: Catalog;
  /** Whether a person is there to answer the main agent's questions (the terminal UI). */
  asks?: boolean;
};

/**
 * The model's context window: the setting, else what its provider reports, else the fallback with a
 * notice saying how to set it.
 */
export async function resolveContextWindow(
  model: ModelRoute,
  deps: ProviderDeps = {},
): Promise<{ window: number; input?: number; output?: number; notice?: string }> {
  const provider = providerOf(model);
  // What the model takes in and writes at most, apart from the window: the catalog's, when it lists it.
  const { input, output } = provider.limits;
  const known = { ...(input ? { input } : {}), ...(output ? { output } : {}) };
  if (model.contextWindow) return { window: model.contextWindow, ...known };
  const reported = await provider.reportedWindow(deps);
  if (reported) return { window: reported, ...known };
  const tokens = MODEL.fallbackContextWindow.toLocaleString("en-US");
  return {
    window: MODEL.fallbackContextWindow,
    notice: provider.windowFromPlan
      ? message("model.windowAssumedPlan", { tokens })
      : message("model.windowAssumed", { tokens, provider: model.provider }),
  };
}

/** A problem for each agent `limits` sets limits for that is not one of the catalog's agents. */
export function agentLimitProblems(limits: Limits, catalog: Catalog = builtinCatalog()): string[] {
  const names = catalog.agents.map((spec) => spec.name);
  return Object.keys(limits.agents)
    .filter((name) => !names.includes(name))
    .map((name) => message("limits.noSuchAgent", { name, agents: names.join(", ") }));
}

/**
 * Who replay data written by `model` may be sent back to: its provider, endpoint and model. A session
 * resumed under another key sends none of what the earlier one attached.
 */
export function modelReplayKey(model: ModelRoute): string {
  return providerOf(model).replayKey;
}

/** The route a session records for `model`: a route that takes a reasoning level records it, the provider's default included. */
export function routeOf(model: ModelRoute): RouteName {
  return {
    provider: model.provider,
    model: model.model,
    ...(model.provider === "openai-compatible" ? {} : { reasoning: model.reasoning ?? "provider-default" }),
  };
}

/**
 * The skills a session offers: the user's own always, the built-in ones only when a built-in agent is
 * offered, since they are written as briefs for the built-in agents.
 */
function offeredSkills<S extends { source: string }>(
  agents: readonly { source: string }[],
  skills: readonly S[],
): S[] {
  const builtInAgent = agents.some((spec) => spec.source === BUILT_IN);
  return skills.filter((skill) => skill.source !== BUILT_IN || builtInAgent);
}

export function createEngine(settings: EngineSettings): Engine {
  // No step asks for more output than the model can write.
  const given = settings.limits ?? DEFAULT_LIMITS;
  // The model's own limits, when the caller resolved none: what its provider knows (the catalog).
  const modelLimits = settings.modelLimits ?? providerOf(settings.model).limits;
  const most = modelLimits.output;
  const limits =
    most === undefined
      ? given
      : {
          ...given,
          output: {
            stepTokens: Math.min(given.output.stepTokens, most),
            finalTokens: Math.min(given.output.finalTokens, most),
          },
        };
  const { model } = settings;
  const provider = providerOf(model);
  const client = provider.client({
    stallMs: limits.modelStallMs,
    ...(settings.chatgptAuthPath ? { chatgptAuthPath: settings.chatgptAuthPath } : {}),
    ...(settings.fetch ? { fetch: settings.fetch } : {}),
    ...(settings.secrets ? { secrets: settings.secrets } : {}),
  });
  const { sampling } = provider;

  const clock: Clock = () => settings.today ?? new Date();
  // The routing table decides which of this setup's providers serves what.
  // A Tauric key adds what Tauric serves, in this setup's own providers without one (not in replayed data).
  const keyFix: KeyFix | undefined =
    settings.providers || settings.tauricKey
      ? undefined
      : {
          app: APP_NAME,
          capabilities: new Set(
            (Object.keys(ROUTES) as Capability[]).filter((capability) =>
              ROUTES[capability].includes("tauric"),
            ),
          ),
        };
  const { capabilities: data, available: served } = route(
    settings.providers ?? dataProviders(settings, clock),
    {
      ...(keyFix ? { keyFix } : {}),
    },
  );
  const offered = dataTools(data, clock);
  // Every tool is offered; one whose data no source here serves says so when called, and the
  // session shows the sign-up nudge then (once).
  const tools = offered.map(([, tool]) => tool);
  const capabilityOf = new Map(offered.map(([capability, tool]) => [tool.name, capability]));
  const hasMarketData = served.has("priceHistory");
  const missing = [...new Set(offered.map(([capability]) => capability))].filter((c) => !served.has(c));
  const registry = new ToolRegistry(tools);

  // The main agent thinks: it gets that mode's sampling, and the server is told to think when it can be.
  const main: AgentSpec = {
    name: "main",
    system: mainPrompt({
      app: APP_NAME,
      missing: missing.map((capability) => CAPABILITY_LABELS[capability]),
      keyAdds:
        Boolean(keyFix) &&
        missing.length > 0 &&
        missing.every((capability) => keyFix?.capabilities.has(capability)),
    }),
    tools: tools.map((tool) => tool.name),
    // The question's limits are applied by the engine for each question.
    caps: { steps: limits.question.steps },
    sampling: { ...sampling.thinking, thinking: true },
    // An answer hurried by a time limit skips thinking, where the model can be told to.
    ...(sampling.canSkipThinking ? { hurriedSampling: { ...sampling.plain, thinking: false } } : {}),
    // The model card's output length for thinking: reasoning comes first, and the answer must still fit.
    maxOutputTokens: limits.output.stepTokens,
    finalOutputTokens: limits.output.finalTokens,
    ...(settings.contextWindow ? { contextWindow: settings.contextWindow } : {}),
    ...(modelLimits.input ? { inputLimit: modelLimits.input } : {}),
  };
  // An agent is offered only when every data tool it names has a source here (a pattern, at least one).
  const available = tools
    .map((tool) => tool.name)
    .filter((name) => {
      const capability = capabilityOf.get(name);
      return capability === undefined || served.has(capability);
    });
  const catalog = settings.catalog ?? builtinCatalog();
  const agents = catalog.agents.flatMap((spec) => {
    const matched = matchTools(spec.tools, available);
    return matched.missing.length
      ? []
      : [{ ...spec, tools: matched.tools, prompt: withSkills(spec, catalog.skills) }];
  });
  const skills = offeredSkills(agents, catalog.skills);
  return new Engine({
    client,
    route: routeOf(model),
    signUpNudge: Boolean(keyFix),
    registry,
    core: (() => {
      const compute = computeTools();
      return [...compute, evidenceTool([...tools, ...compute])];
    })(),
    main,
    agents,
    skills,
    limits,
    version: settings.version,
    now: clock,
    summarySampling: { ...sampling.plain, thinking: false },
    ...(settings.asks ? { asks: true } : {}),
    ...(settings.dataDir
      ? {
          memory: new Memory(settings.dataDir, {
            client,
            sampling: { ...sampling.plain, thinking: false },
            clock,
            ...(hasMarketData ? { closes: closesFrom(data.priceHistory) } : {}),
          }),
        }
      : {}),
    ...(settings.session ? { session: settings.session } : {}),
    ...(settings.restore ? { restore: settings.restore } : {}),
    ...(settings.evidence ? { evidence: settings.evidence } : {}),
  });
}

/** The providers a setup has: Tauric with a key; Yahoo and Polymarket need none. */
export function dataProviders(
  settings: Pick<EngineSettings, "tauricKey" | "fetch">,
  clock: Clock = () => new Date(),
): Providers {
  return {
    ...(settings.tauricKey
      ? {
          tauric: tauricProvider(
            new TauricClient({
              apiKey: settings.tauricKey,
              ...(settings.fetch ? { fetch: settings.fetch } : {}),
            }),
          ),
        }
      : {}),
    yahoo: yahooProvider({ now: clock, ...(settings.fetch ? { fetch: settings.fetch } : {}) }),
    polymarket: polymarketProvider(new PolymarketClient(settings.fetch ?? fetch)),
  };
}

/** Daily closes for settling decisions, a listing and its benchmark from one source; final only when it will not revise them. */
function closesFrom(history: PriceHistory): ClosesSource {
  return async (symbols, from, to, signal) => {
    const answer = await history.dailyPair(symbols, { from, to }, signal ? { signal } : {});
    // A session without a close stays in the list, so it cannot shift the observation window.
    const closesOf = (bars: DailyBars) => ({
      closes: bars.bars.map((bar) => ({
        date: bar.date,
        close: bar.close ?? null,
        final: bar.revision === "final",
      })),
      basis: bars.price_basis ?? "basis not stated",
    });
    return { stock: closesOf(answer.data[0]), benchmark: closesOf(answer.data[1]), source: answer.source };
  };
}

/** Tauric, where sessions are copied when sync is on, under this application's own name. */
export function tauricSessions(apiKey: string, fetchImpl?: typeof globalThis.fetch): RemoteSessions {
  const client = new TauricApplications({
    apiKey,
    application: APP_NAME,
    ...(fetchImpl ? { fetch: fetchImpl } : {}),
  });
  return {
    application: APP_NAME,
    async accepts(call) {
      const { storage } = await client.account(call);
      return storage.applications.some((application) => application.id === APP_NAME);
    },
    async describe(id, call) {
      try {
        const { size, metadata } = await client.session(id, call);
        return { size, metadata };
      } catch (error) {
        // Only Tauric's own "not found" means no such session: sync asks this only once the account
        // is known to keep this application's sessions, which a missing application answers the same.
        // Any other 404 is not taken for an absence.
        if (error instanceof DataError && error.details.status === 404 && error.details.code === "not_found")
          return undefined;
        throw error;
      }
    },
    async list(limit, call) {
      const found: RemoteSummary[] = [];
      let after: string | null = null;
      // Pages until the end or SYNC.listedPages of them; the newest of those are kept.
      for (let page = 0; page < SYNC.listedPages; page++) {
        let listed: Awaited<ReturnType<typeof client.listSessions>>;
        try {
          listed = await client.listSessions({ limit: 100, ...(after ? { after } : {}) }, call);
        } catch (error) {
          // An account that does not keep this application's sessions has none.
          if (
            error instanceof DataError &&
            error.details.status === 404 &&
            error.details.code === "not_found"
          )
            break;
          throw error;
        }
        for (const one of listed.data) {
          found.push({
            id: one.id,
            created: one.created_at,
            updated: new Date(one.last_append_at ?? one.updated_at),
            size: one.size,
            // Any client of the account may write it: shown only as printable text.
            title: printable(one.metadata.title ?? ""),
          });
        }
        after = listed.next_cursor;
        if (!after) break;
      }
      return found.sort((a, b) => b.updated.getTime() - a.updated.getTime()).slice(0, limit);
    },
    putSession: (id, metadata, call) => client.putSession(id, metadata, call),
    readSession: (id, start, end, call) => client.readSession(id, start, end, call),
    deleteSession: (id) => client.deleteSession(id),
    append: (id, offset, lines, call) => client.append(id, offset, lines, call),
  };
}

/** The ChatGPT sign-in kept at `path`; the commands and the model client share it. */
export function chatgptAuth(path: string | undefined, fetchImpl?: typeof globalThis.fetch): ChatGPTAuth {
  if (!path) throw new Error("a ChatGPT sign-in needs the path of its file");
  return new ChatGPTAuth({ path, ...(fetchImpl ? { fetch: fetchImpl } : {}) });
}
