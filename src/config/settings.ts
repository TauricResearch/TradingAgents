// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The user's settings, from `config.json` and `credentials.json` in the home directory, with
 * environment variables taking precedence field by field (flags over both), and the writers of
 * `config.json`. Nothing has a public default endpoint: an unset model is reported, and the CLI says
 * how to set it. Loading reads and creates nothing else.
 *
 * Problems name the field and the source, never a value: a credential never reaches a message.
 */

import { promises as fs } from "node:fs";
import { z } from "zod";
import {
  APP_NAME,
  endpointOf,
  HOSTED_PROVIDERS,
  type HostedProvider,
  type ModelRoute,
  message,
  PROVIDER_IDS,
  type ProviderId,
  REASONING_LEVELS,
  type ReasoningLevel,
  type RouteName,
  type SamplingSettings,
} from "../contracts/index.js";
import { KEYS, type Limits } from "../contracts/limits.js";
import { UnsafeFileError, writePrivate } from "../store/index.js";
import { type CredentialName, credentialKey, readCredentials, writeCredentials } from "./credentials.js";
import { ENV, KEY_VARS } from "./env.js";
import { isRecord, parseJson, pick } from "./json.js";
import { resolveLimits } from "./limits.js";
import { CONFIG_FILE, type Paths, resolvePaths } from "./paths.js";

const sampling = z
  .object({
    temperature: z.number().min(0).max(2).optional(),
    topP: z.number().gt(0).max(1).optional(),
    topK: z.number().int().positive().optional(),
    presencePenalty: z.number().min(-2).max(2).optional(),
  })
  .strict();

/** The model's context window in tokens, when its provider does not report it. */
const contextWindow = z.number().int().min(4_096);

/** An OpenAI-compatible server's settings, each checked on its own: one bad field drops only itself. */
const serverFields = {
  baseURL: z.string().min(1),
  /** How the server is told to think: vLLM-style chat template switch, or not at all. */
  thinking: z.enum(["chat-template", "none"]),
  /** Model-card sampling for each mode; unset values are left to the server. */
  sampling: z.object({ thinking: sampling.optional(), plain: sampling.optional() }).strict(),
  contextWindow,
};
type ServerFields = { [K in keyof typeof serverFields]?: z.infer<(typeof serverFields)[K]> };

/** The settings a provider block may hold: a server's for the compatible provider, a window for any. */
const providerFields: Record<ProviderId, Record<string, z.ZodType>> = {
  tauric: { contextWindow },
  chatgpt: { contextWindow },
  "openai-compatible": serverFields,
  openai: { contextWindow },
  anthropic: { contextWindow },
  google: { contextWindow },
  deepseek: { contextWindow },
  openrouter: { contextWindow },
};
type ProviderBlocks = { "openai-compatible"?: ServerFields } & {
  [P in Exclude<ProviderId, "openai-compatible">]?: { contextWindow?: number };
};

export type Settings = {
  /** Undefined until a model is set that can be reached (a key for a hosted one, a base URL for a server). */
  model?: ModelRoute;
  /**
   * The providers that can be used without signing in: a hosted one with a key, a server with its address
   * and a model. A ChatGPT plan is known by its sign-in, which the caller checks.
   */
  connected: ProviderId[];
  /** The model named by a flag, the environment or the file, whether or not it can be reached. */
  choice?: RouteName;
  /**
   * Where a model was named, also one that could not be read (then no other is picked): "--model", the
   * environment variable, or the config file; undefined when none was.
   */
  namedBy?: string;
  tauricKey?: string;
  /** Whether sessions are copied to Tauric. Off unless set on; an unreadable value is off. */
  sync: boolean;
  /** Whether sync was set at all (on or off); until it is, an interactive run asks. */
  syncAsked: boolean;
  /** Every key found, whichever one is used: the credentials the app holds, scrubbed from model errors. */
  keys: string[];
  /** Where each key used was found: its environment variable, or "stored" (no values). */
  keyFrom: Partial<Record<HostedProvider, string>>;
  /** What a question and its agents may use: config.json `limits`, then any given on the command line. */
  limits: Limits;
  /** What could not be used and why, without values; the CLI shows these. */
  problems: string[];
};

export async function loadSettings(
  env: NodeJS.ProcessEnv = process.env,
  {
    limits: given,
    flags = {},
    paths = resolvePaths(env),
  }: {
    limits?: unknown;
    /** The model and reasoning given on the command line, over the environment's and the file's. */
    flags?: { model?: string; reasoning?: string };
    /** Where the files are, when resolved already; else from `env`. */
    paths?: Paths;
  } = {},
): Promise<Settings> {
  const problems: string[] = [];
  const file = await readConfigFile(paths.config, problems);
  const { modelEndpoint: storedEndpoint, ...credentials } = await readCredentials(
    paths.credentials,
    problems,
  );
  const fromEnv = (name: string): string | undefined => {
    const value = env[name];
    if (value === undefined) return undefined;
    if (!value.trim()) {
      problems.push(message("config.emptyVariable", { name }));
      return undefined;
    }
    return value.trim();
  };

  const keyFromEnv = (name: string) => {
    const value = fromEnv(name);
    if (value !== undefined && !credentialKey.safeParse(value).success) {
      problems.push(message("config.keyTooShort", { name }));
      return undefined;
    }
    return value;
  };
  const envModelKey = keyFromEnv(ENV.modelKey);
  // Each hosted provider's key: the first of its variables that is set, else the stored one. Each
  // variable is read once, so one that cannot be used is named once.
  const keyFrom: Settings["keyFrom"] = {};
  const hostedKeys = Object.fromEntries(
    HOSTED_PROVIDERS.map((provider) => {
      for (const variable of KEY_VARS[provider]) {
        const value = keyFromEnv(variable);
        if (value === undefined) continue;
        keyFrom[provider] = variable;
        return [provider, value];
      }
      if (credentials[provider] !== undefined) keyFrom[provider] = "stored";
      return [provider, credentials[provider]];
    }),
  ) as { [P in HostedProvider]?: string };
  // Tauric's key serves its data as well as its model.
  const tauricKey = hostedKeys.tauric;

  // "provider-default" leaves it to the provider, over a level the file sets.
  const reasoningSetting = flags.reasoning ?? file.reasoning;
  let reasoning: ReasoningLevel | undefined;
  if (reasoningSetting !== undefined && reasoningSetting !== "provider-default") {
    if ((REASONING_LEVELS as readonly unknown[]).includes(reasoningSetting))
      reasoning = reasoningSetting as ReasoningLevel;
    else
      problems.push(
        message("config.badReasoning", {
          where: flags.reasoning !== undefined ? "--reasoning" : CONFIG_FILE,
          levels: REASONING_LEVELS.join(", "),
        }),
      );
  }

  // The model: a base URL in the environment chooses an OpenAI-compatible server (with the model the
  // environment names, as the server names it); else a model the environment names as "provider/id";
  // else the file's.
  const envBaseURL = fromEnv(ENV.baseURL);
  const envModel = fromEnv(ENV.model);
  const server = file.providers?.["openai-compatible"] ?? {};
  let choice: RouteName | undefined;
  if (flags.model !== undefined) {
    choice = parseChoice(flags.model, (problem) =>
      problems.push(message("config.badModel", { where: "--model", problem })),
    );
  } else if (
    envBaseURL !== undefined &&
    (envModel !== undefined || file.model?.provider === "openai-compatible")
  ) {
    // A server's address in the environment chooses the server when a model for it is named (there or in
    // the file); the model as the server names it may hold slashes of its own, and its provider may lead it.
    const fromEnv = envModel?.startsWith("openai-compatible/")
      ? envModel.slice("openai-compatible/".length)
      : envModel;
    const named = fromEnv ?? (file.model?.provider === "openai-compatible" ? file.model.model : undefined);
    choice = named === undefined ? undefined : { provider: "openai-compatible", model: named };
  } else if (envModel !== undefined) {
    choice = parseChoice(envModel, (problem) =>
      problems.push(message("config.badModel", { where: ENV.model, problem })),
    );
  } else choice = file.model;

  let model: ModelRoute | undefined;
  const levels = reasoning ? { reasoning } : {};
  if (choice?.provider === "chatgpt") {
    const window = file.providers?.chatgpt?.contextWindow;
    model = {
      provider: "chatgpt",
      model: choice.model,
      ...levels,
      ...(window ? { contextWindow: window } : {}),
    };
  } else if (choice && (HOSTED_PROVIDERS as readonly string[]).includes(choice.provider)) {
    const provider = choice.provider as HostedProvider;
    const apiKey = hostedKeys[provider];
    const window = file.providers?.[provider]?.contextWindow;
    if (apiKey === undefined)
      problems.push(
        message("config.noKey", { provider, vars: KEY_VARS[provider].join(" or "), app: APP_NAME }),
      );
    else
      model = {
        provider,
        model: choice.model,
        apiKey,
        ...levels,
        ...(window ? { contextWindow: window } : {}),
      };
  } else if (choice?.provider === "openai-compatible") {
    const baseURL = envBaseURL ?? server.baseURL;
    const endpoint = baseURL === undefined ? undefined : checkEndpoint(baseURL);
    if (baseURL === undefined) problems.push(message("config.noBaseUrl", { var: ENV.baseURL }));
    else if (endpoint) problems.push(message("config.badBaseUrl", { problem: endpoint }));
    else {
      // A stored key goes only to the server it was stored for; the environment's goes where it says.
      const stored = credentials.model;
      const boundHere = stored !== undefined && storedEndpoint === endpointOf(baseURL);
      if (stored !== undefined && !boundHere && envModelKey === undefined)
        problems.push(
          message("config.keyForOtherServer", {
            endpoint: storedEndpoint ?? "",
            app: APP_NAME,
          }),
        );
      const modelKey = envModelKey ?? (boundHere ? stored : undefined);
      model = {
        provider: "openai-compatible",
        baseURL,
        model: choice.model,
        thinking: server.thinking ?? "none",
        sampling: {
          thinking: setOnly(server.sampling?.thinking),
          plain: setOnly(server.sampling?.plain),
        },
        ...(server.contextWindow ? { contextWindow: server.contextWindow } : {}),
        ...(modelKey ? { apiKey: modelKey } : {}),
      };
    }
  }
  // Sync uploads sessions, so it is on only when a setting says exactly "on"; anything else is off.
  // A variable that is set decides, even when empty (then off).
  const syncFromEnv = env[ENV.sync] !== undefined;
  const syncSetting = syncFromEnv ? env[ENV.sync] : file.sync;
  if (syncSetting !== undefined && syncSetting !== "" && syncSetting !== "on" && syncSetting !== "off") {
    problems.push(message("config.badSync", { where: syncFromEnv ? ENV.sync : CONFIG_FILE }));
  }
  const sync = syncSetting === "on";
  const syncAsked = syncFromEnv || file.sync === "on" || file.sync === "off";
  // Every key found, also those another one shadows.
  const keys = [
    ...new Set(
      [
        env[ENV.modelKey],
        ...Object.values(KEY_VARS).flatMap((names) => names.map((name) => env[name])),
        ...Object.values(credentials),
      ]
        .map((value) => value?.trim())
        .filter((value): value is string => Boolean(value)),
    ),
  ];
  const serverReady =
    choice?.provider === "openai-compatible" && (envBaseURL ?? server.baseURL) !== undefined;
  const connected = PROVIDER_IDS.filter((provider) =>
    provider === "openai-compatible"
      ? serverReady
      : (HOSTED_PROVIDERS as readonly string[]).includes(provider) &&
        hostedKeys[provider as HostedProvider] !== undefined,
  );
  const resolved = resolveLimits(file.limits, given);
  problems.push(...resolved.problems);
  return {
    ...(model ? { model } : {}),
    connected,
    ...(choice ? { choice } : {}),
    ...(flags.model !== undefined
      ? { namedBy: "--model" }
      : envModel !== undefined
        ? { namedBy: ENV.model }
        : file.modelNamed
          ? { namedBy: CONFIG_FILE }
          : {}),
    ...(tauricKey ? { tauricKey } : {}),
    sync,
    syncAsked,
    keys,
    keyFrom,
    limits: resolved.limits,
    problems,
  };
}

/** Store one credential, keeping the others. Refuses to overwrite a credentials file it cannot read. */
export async function saveCredential(
  name: CredentialName,
  value: string,
  paths: Paths,
  {
    endpoint,
    env = process.env,
  }: {
    /** The server a `model` key is for, when not the one configured now. */
    endpoint?: string;
    /** Where the configured server's address may be set (TRADINGAGENTS_BASE_URL), for a `model` key. */
    env?: NodeJS.ProcessEnv;
  } = {},
) {
  const secret = value.trim();
  if (!secret || /[\r\n]/.test(secret)) throw new Error(message("config.keyOneLine"));
  if (!credentialKey.safeParse(secret).success)
    throw new Error(message("config.keyLength", { min: KEYS.minChars }));
  // A server's key is bound to the server it is stored for: its address must be set first.
  let bound: { modelEndpoint: string } | Record<string, never> = {};
  if (name === "model") {
    const baseURL =
      endpoint ??
      (env[ENV.baseURL]?.trim() ||
        (await readConfigFile(paths.config, [])).providers?.["openai-compatible"]?.baseURL);
    if (!baseURL) throw new Error(message("config.serverFirst", { var: ENV.baseURL }));
    bound = { modelEndpoint: endpointOf(baseURL) };
  }
  const path = paths.credentials;
  await writeCredentials(path, { [name]: secret, ...bound });
  return path;
}

async function readConfigFile(
  path: string,
  problems: string[],
): Promise<{
  model?: RouteName;
  providers?: ProviderBlocks;
  sync?: unknown;
  limits?: unknown;
  reasoning?: unknown;
  modelNamed?: boolean;
}> {
  let text: string;
  try {
    text = await fs.readFile(path, "utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT")
      problems.push(message("config.unreadable", { path }));
    return {};
  }
  const json = parseJson(text);
  if (!isRecord(json)) {
    problems.push(message("config.notObject", { path }));
    return {};
  }
  const { model, providers } = json;
  const out: {
    model?: RouteName;
    providers?: ProviderBlocks;
    sync?: unknown;
    limits?: unknown;
    reasoning?: unknown;
    modelNamed?: boolean;
  } = {
    ...(json.reasoning === undefined ? {} : { reasoning: json.reasoning }),
    ...(model === undefined ? {} : { modelNamed: true }),
    ...(json.sync === undefined ? {} : { sync: json.sync }),
    ...(json.limits === undefined ? {} : { limits: json.limits }),
  };
  if (typeof model === "string") {
    const choice = parseChoice(model, (problem) =>
      problems.push(message("config.badModel", { where: path, problem })),
    );
    if (choice) out.model = choice;
  } else if (model !== undefined) problems.push(message("config.invalidModel", { path }));
  if (providers === undefined) return out;
  if (!isRecord(providers)) {
    problems.push(message("config.invalidProviders", { path }));
    return out;
  }
  const blocks: Record<string, unknown> = {};
  for (const [id, block] of Object.entries(providers)) {
    if (!PROVIDER_IDS.includes(id as ProviderId)) {
      // Not named back: it could be anything pasted there.
      problems.push(message("config.unknownProviderBlock", { path, providers: PROVIDER_IDS.join(", ") }));
      continue;
    }
    const fields = providerFields[id as ProviderId];
    if (!isRecord(block)) {
      problems.push(message("config.invalidProvider", { path, provider: id }));
      continue;
    }
    blocks[id] = pick(
      block,
      fields,
      (field) => message("config.invalidProviderField", { path, provider: id, field }),
      problems,
    );
  }
  out.providers = blocks as ProviderBlocks;
  return out;
}

/** "provider/id" read: split at the first slash, so a server's own slashes stay in the id. */
function parseChoice(text: string, problem: (text: string) => void): RouteName | undefined {
  const at = text.indexOf("/");
  const provider = text.slice(0, Math.max(at, 0));
  const model = text.slice(at + 1).trim();
  if (at < 0 || !model) {
    problem(message("config.modelForm", { providers: PROVIDER_IDS.join(", ") }));
    return undefined;
  }
  if (!PROVIDER_IDS.includes(provider as ProviderId)) {
    problem(message("config.unknownProvider", { providers: PROVIDER_IDS.join(", ") }));
    return undefined;
  }
  return { provider: provider as ProviderId, model };
}

function setOnly(values: z.infer<typeof sampling> | undefined): SamplingSettings {
  return Object.fromEntries(Object.entries(values ?? {}).filter(([, value]) => value !== undefined));
}

/** Why a base URL cannot be used, or undefined when it can. */
export function checkEndpoint(value: string): string | undefined {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return message("config.notAUrl");
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return message("config.urlScheme");
  if (url.username || url.password) return message("config.urlCredentials");
  return undefined;
}

/** Turn session sync on or off in the config file, keeping its other settings. */
export function saveSync(on: boolean, paths: Paths): Promise<string> {
  return rewriteConfig(paths, (current) => ({ ...current, sync: on ? "on" : "off" }));
}

/**
 * Use `choice` and its reasoning from now on, saved together in one write (a choice without reasoning
 * clears the setting), keeping the config file's other settings.
 */
export function saveModel(choice: RouteName, paths: Paths): Promise<string> {
  return rewriteConfig(paths, (current) => {
    const { reasoning: _, ...rest } = current;
    return {
      ...rest,
      model: `${choice.provider}/${choice.model}`,
      ...(choice.reasoning ? { reasoning: choice.reasoning } : {}),
    };
  });
}

/**
 * Use an OpenAI-compatible server from now on: its address and model in the config file, and its key, when
 * given, kept for that address. A bad address is refused before anything is written.
 */
export async function saveServer(
  server: { baseURL: string; model: string },
  apiKey: string | undefined,
  paths: Paths,
): Promise<string> {
  const problem = checkEndpoint(server.baseURL);
  if (problem) throw new Error(problem);
  // A key that cannot be stored stops the save before anything is written.
  if (apiKey !== undefined && !credentialKey.safeParse(apiKey).success) {
    throw new Error(message("config.keyLength", { min: KEYS.minChars }));
  }
  const path = await rewriteConfig(paths, (current) => {
    const blocks = isRecord(current.providers) ? current.providers : {};
    const block = isRecord(blocks["openai-compatible"]) ? blocks["openai-compatible"] : {};
    return {
      ...current,
      model: `openai-compatible/${server.model}`,
      providers: { ...blocks, "openai-compatible": { ...block, baseURL: server.baseURL } },
    };
  });
  if (apiKey) await saveCredential("model", apiKey, paths, { endpoint: server.baseURL });
  return path;
}

/** Rewrite the config file through `change`, owner-only; refuses a symbolic link or a file that is not a JSON object. */
async function rewriteConfig(
  paths: Paths,
  change: (current: Record<string, unknown>) => Record<string, unknown>,
): Promise<string> {
  const path = paths.config;
  // Writing replaces the file, which would turn a link into a file of its own.
  const linked = await fs.lstat(path).then(
    (stat) => stat.isSymbolicLink(),
    () => false,
  );
  if (linked) throw new UnsafeFileError(message("file.symlink", { path }));
  let current: Record<string, unknown> = {};
  try {
    const parsed = parseJson(await fs.readFile(path, "utf8"));
    if (!isRecord(parsed)) throw new Error(message("config.notObjectFixFirst", { path }));
    current = parsed;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
  // Owner only, like the credentials: it names the model server requests go to.
  await writePrivate(path, `${JSON.stringify(change(current), null, 2)}\n`);
  return path;
}
