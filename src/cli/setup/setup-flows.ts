// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The setups, as steps over a FormUI: the first run (where answers come from, its key or sign-in, the
 * model and how hard it reasons, then a Tauric key for data when another provider was chosen), `/login`
 * (one provider's key or sign-in) and `/model` (a provider, connected in place when it is not yet, then
 * the model new sessions use). Esc goes back one step; Ctrl+C ends a setup,
 * keeping what it saved, and a key is saved as soon as it is given. Nothing is checked over the network:
 * a key that does not work says so on first use.
 */
import { type CredentialName, checkEndpoint } from "../../config/index.js";
import {
  APP_NAME,
  HOSTED_PROVIDERS,
  type HostedProvider,
  message,
  PROVIDER_IDS,
  PROVIDER_LABELS,
  type ProviderId,
  type ReasoningLevel,
  type RouteName,
} from "../../contracts/index.js";
import { type ModelOption, modelsOf, offeredLevels, RECOMMENDED } from "../../engine/index.js";
import type { FieldBuffer } from "../form/field-state.js";
import { BACK, FlowCancelledError, type FormUI } from "../form/form-ui.js";
import type { PickerOption } from "../form/picker-state.js";

/** What a setup knows when it starts. */
export type SetupFacts = {
  /** Whether a ChatGPT sign-in that may use the plan is there. */
  signedIn: boolean;
  /** Where each key already found came from: its environment variable, or "stored". */
  keyFrom: Partial<Record<HostedProvider, string>>;
  /** The providers that can be used now (a key found, or a server with its model). */
  connected: readonly ProviderId[];
  /** The server's model, when one is set up. */
  serverModel?: string;
  /** The model this session runs on. */
  current?: RouteName;
  /** Where the model is named instead of the config file (an environment variable, --model), if it is. */
  modelNamedBy?: string;
};

/** What a setup does; each saves at once and says nothing of a value. */
export type SetupActions = {
  /** Store a key, taking it from the field. */
  saveKey(name: CredentialName, key: FieldBuffer): Promise<void>;
  /** Store a server's address and model, and its key when one was given. */
  saveServer(server: { baseURL: string; model: string }, key?: FieldBuffer): Promise<void>;
  /** Use this model, and how hard it reasons, from now on. */
  saveModel(choice: RouteName): Promise<void>;
  /** Sign in to ChatGPT; false when it did not finish. Absent where it cannot run (inside the chat). */
  signIn?(): Promise<boolean>;
  /** The models the ChatGPT plan offers. */
  planModels(): Promise<{ id: string; name: string }[]>;
};

/** A step: what comes next, BACK, or the lines a finished setup says. `skip` comes next but is left out on the way back. */
type Step = () => Promise<Step | { skip: Step } | typeof BACK | { done: string[] }>;

async function run(first: Step): Promise<string[]> {
  const stack: Step[] = [first];
  for (;;) {
    const step = stack.at(-1);
    if (!step) throw new FlowCancelledError();
    const next = await step();
    if (next === BACK) stack.pop();
    else if ("done" in next) return next.done;
    else if ("skip" in next) {
      stack.pop();
      stack.push(next.skip);
    } else stack.push(next);
  }
}

/** A model family by its maker's name, where a provider serves several (OpenRouter). */
const FAMILY: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  google: "Google",
  deepseek: "DeepSeek",
};

const isHosted = (provider: string): provider is HostedProvider =>
  (HOSTED_PROVIDERS as readonly string[]).includes(provider);

/** Whether `provider` can be used now: the session's, signed in, a key found, or a server with its model. */
function isReady(facts: SetupFacts, provider: ProviderId): boolean {
  // The session runs on it, whatever named it.
  if (facts.current?.provider === provider) return true;
  if (provider === "chatgpt") return facts.signedIn;
  if (isHosted(provider)) return facts.keyFrom[provider] !== undefined;
  return facts.connected.includes(provider) && facts.serverModel !== undefined;
}

/**
 * Every provider, in the order offered: those ready to use marked, and for `/model` the current one and
 * those to connect ("Connect"); a first setup marks the one it recommends.
 */
function providerOptions(facts: SetupFacts, setup: "first" | "login" | "model"): PickerOption[] {
  return PROVIDER_IDS.map((provider) => {
    const note =
      setup === "model" && facts.current?.provider === provider
        ? message("setup.current")
        : isReady(facts, provider)
          ? message(provider === "chatgpt" ? "setup.signedIn" : "setup.ready")
          : setup === "first" && provider === RECOMMENDED
            ? message("setup.recommended")
            : setup === "model"
              ? message("setup.connect")
              : undefined;
    return {
      id: provider,
      label: PROVIDER_LABELS[provider],
      detail: message(`setup.about.${provider}` as "setup.about.openai"),
      ...(note ? { note } : {}),
    };
  });
}

/** A model option: its name, the current, default or fast one marked, its family as its group, with its window, price and levels as the detail. */
function modelOption(
  provider: ProviderId,
  model: Pick<ModelOption, "id" | "name" | "family" | "context" | "cost"> & {
    role?: ModelOption["role"];
    reasoning?: ReasoningLevel[];
  },
  current?: RouteName,
): PickerOption {
  const isCurrent = current?.provider === provider && current.model === model.id;
  const detail = [
    model.context ? message("setup.context", { tokens: model.context }) : "",
    model.cost ? message("setup.cost", model.cost) : "",
    model.reasoning?.length
      ? message("setup.levels", {
          least: model.reasoning[0] as string,
          most: model.reasoning.at(-1) as string,
        })
      : "",
  ].filter(Boolean);
  const note = isCurrent
    ? message("setup.current")
    : model.role === "default"
      ? message("setup.default")
      : model.role === "fast"
        ? message("setup.fast")
        : undefined;
  return {
    id: model.id,
    label: model.name,
    detail: detail.join(", "),
    ...(note ? { note } : {}),
    ...(model.family ? { group: FAMILY[model.family] ?? model.family } : {}),
  };
}

/** The levels to choose from: the provider's default first, then those the model offers. */
function reasoningOptions(provider: ProviderId, model: string): PickerOption[] {
  return [
    { id: "provider-default", label: message("setup.providerDefault") },
    ...offeredLevels(provider, model).map((level) => ({ id: level, label: level })),
  ];
}

/**
 * Ask for a key for `name` and save it; BACK leaves it unsaved. A Tauric key asked for after another
 * provider was chosen is asked for its data.
 */
async function askKey(
  ui: FormUI,
  actions: SetupActions,
  name: CredentialName,
  { optional = false, forData = false }: { optional?: boolean; forData?: boolean } = {},
) {
  const title =
    forData || name === "tauric"
      ? message("setup.tauricKey")
      : message("setup.keyFor", { provider: PROVIDER_LABELS[name as HostedProvider] ?? name });
  const field = await ui.field({
    title,
    kind: "secret",
    ...(optional ? { hint: message("setup.skipHint") } : {}),
  });
  if (field === BACK) return BACK;
  if (field.shown().text === "") {
    field.clear();
    return optional ? "skipped" : "empty";
  }
  await actions.saveKey(name, field);
  return "saved";
}

/**
 * The models the ChatGPT plan offers, with the catalog's roles and levels; the catalog's list when the
 * plan cannot be read.
 */
async function planOptions(actions: SetupActions): Promise<Parameters<typeof modelOption>[1][]> {
  const catalog = modelsOf("chatgpt");
  const plan = await actions.planModels().catch(() => undefined);
  if (!plan?.length) return catalog;
  return plan.map((entry) => {
    const role = catalog.find((listed) => listed.id === entry.id)?.role;
    return { ...entry, ...(role ? { role } : {}), reasoning: offeredLevels("chatgpt", entry.id) };
  });
}

/**
 * `provider`'s models to choose from, then how hard the one chosen reasons; the choice is saved, and
 * `then` comes next. Steps with nothing to choose are left out on the way back.
 */
function modelSteps(
  ui: FormUI,
  facts: SetupFacts,
  actions: SetupActions,
  provider: ProviderId,
  then: (model: string) => Step,
): Step {
  const { current } = facts;
  const reasoning =
    (model: string): Step =>
    async () => {
      const options = provider === "openai-compatible" ? [] : reasoningOptions(provider, model);
      let level: string | typeof BACK = "provider-default";
      if (options.length > 1) {
        level = await ui.pick({
          title: message("setup.chooseReasoning"),
          options,
          start:
            current?.provider === provider && current.model === model
              ? (current.reasoning ?? "provider-default")
              : "provider-default",
        });
        if (level === BACK) return BACK;
      }
      await actions.saveModel({
        provider,
        model,
        ...(level === "provider-default" ? {} : { reasoning: level as ReasoningLevel }),
      });
      return options.length > 1 ? then(model) : { skip: then(model) };
    };
  return async () => {
    const listed: Parameters<typeof modelOption>[1][] =
      provider === "chatgpt"
        ? await planOptions(actions)
        : provider === "openai-compatible"
          ? facts.serverModel
            ? [{ id: facts.serverModel, name: facts.serverModel }]
            : []
          : modelsOf(provider);
    // The session's own model is there to keep, also when the list does not name it.
    if (current?.provider === provider && !listed.some((entry) => entry.id === current.model))
      listed.unshift({ id: current.model, name: current.model });
    const start =
      current?.provider === provider
        ? current.model
        : (listed.find((entry) => entry.role === "default") ?? listed[0])?.id;
    const chosen = await ui.pick({
      title: message("setup.chooseModel"),
      filter: true,
      options: listed.map((entry) => modelOption(provider, entry, current)),
      ...(start ? { start } : {}),
    });
    if (chosen === BACK) return BACK;
    return reasoning(chosen);
  };
}

/** Text that looks like an API key (OpenAI's, Anthropic's, OpenRouter's, Google's, Tauric's): not an address or a model. */
function looksLikeKey(text: string): boolean {
  return /(^|[^A-Za-z0-9])(sk-|tk_|AIza)[A-Za-z0-9_-]{8,}/.test(text);
}

/** A server's address, model and optional key, saved together once all are given; then what `then` gives for it. */
function serverSteps(ui: FormUI, actions: SetupActions, then: (model: string) => Step): Step {
  const server = { baseURL: "", model: "" };
  let problem: string | undefined;
  const address: Step = async () => {
    const field = await ui.field({
      title: problem ? message("setup.serverAddressAgain", { problem }) : message("setup.serverAddress"),
      kind: "text",
      initial: server.baseURL,
    });
    if (field === BACK) return BACK;
    server.baseURL = field.take();
    problem = !server.baseURL
      ? undefined
      : looksLikeKey(server.baseURL)
        ? message("setup.looksLikeKey")
        : checkEndpoint(server.baseURL);
    if (problem && looksLikeKey(server.baseURL)) server.baseURL = "";
    return server.baseURL && !problem ? modelId : address;
  };
  let modelProblem: string | undefined;
  const modelId: Step = async () => {
    const field = await ui.field({
      title: modelProblem ?? message("setup.serverModel"),
      kind: "text",
      initial: looksLikeKey(server.model) ? "" : server.model,
    });
    if (field === BACK) return BACK;
    server.model = field.take();
    modelProblem = looksLikeKey(server.model) ? message("setup.looksLikeKey") : undefined;
    return server.model && !modelProblem ? key : modelId;
  };
  const key: Step = async () => {
    const field = await ui.field({
      title: message("setup.serverKey"),
      kind: "secret",
      hint: message("setup.skipHint"),
    });
    if (field === BACK) return BACK;
    const given = field.shown().text !== "";
    if (!given) field.clear();
    await actions.saveServer(server, given ? field : undefined);
    return { skip: then(server.model) };
  };
  return address;
}

export function firstRun(ui: FormUI, facts: SetupFacts, actions: SetupActions): Promise<string[]> {
  // What is known, with the keys saved on the way.
  const known: SetupFacts = { ...facts, keyFrom: { ...facts.keyFrom } };
  const tauric: Step = async () => {
    if (known.keyFrom.tauric !== undefined) return { done: [] };
    const saved = await askKey(ui, actions, "tauric", { optional: true, forData: true });
    return saved === BACK ? BACK : { done: [] };
  };
  const credentials =
    (provider: ProviderId): Step =>
    async () => {
      const models = modelSteps(ui, facts, actions, provider, () => tauric);
      if (provider === "chatgpt") {
        if (facts.signedIn) return { skip: models };
        // Signing in goes to the browser and back: on the way back, the step before it.
        const signedIn = (await actions.signIn?.()) ?? false;
        return signedIn ? { skip: models } : BACK;
      }
      if (provider === "openai-compatible") return { skip: serverSteps(ui, actions, () => tauric) };
      if (!isHosted(provider)) return BACK;
      const enter: Step = async () => {
        const saved = await askKey(ui, actions, provider);
        if (saved === "saved") known.keyFrom[provider] = "stored";
        return saved === BACK ? BACK : saved === "empty" ? { skip: enter } : models;
      };
      const from = facts.keyFrom[provider];
      if (!from) return { skip: enter };
      const choice = await ui.pick({
        title: from === "stored" ? message("setup.keyStored") : message("setup.keyInEnv", { variable: from }),
        options: [
          { id: "use", label: message("setup.useIt") },
          { id: "another", label: message("setup.enterAnother") },
        ],
      });
      if (choice === BACK) return BACK;
      return choice === "use" ? models : enter;
    };
  const provider: Step = async () => {
    const start = RECOMMENDED;
    const chosen = await ui.pick({
      title: message("setup.chooseProvider"),
      options: providerOptions(facts, "first"),
      // The flow's first step: Esc ends it. Eight providers: typing finds one.
      filter: true,
      esc: "close",
      ...(start ? { start } : {}),
    });
    if (chosen === BACK) return BACK;
    return credentials(chosen as ProviderId);
  };
  return run(provider);
}

export function loginFlow(ui: FormUI, facts: SetupFacts, actions: SetupActions): Promise<string[]> {
  const envWins = (name: HostedProvider) => {
    const from = facts.keyFrom[name];
    return from && from !== "stored" ? [message("cli.envKeyWins", { variable: from })] : [];
  };
  const provider: Step = async () => {
    const chosen = await ui.pick({
      title: message("setup.chooseLogin"),
      options: providerOptions(facts, "login"),
      // The flow's first step: Esc ends it. Eight providers: typing finds one.
      filter: true,
      esc: "close",
    });
    if (chosen === BACK) return BACK;
    if (chosen === "chatgpt") {
      if (!actions.signIn) return { done: [message("setup.signInElsewhere", { app: APP_NAME })] };
      return (await actions.signIn())
        ? { done: [message("setup.connected", { provider: PROVIDER_LABELS.chatgpt })] }
        : provider;
    }
    if (chosen === "openai-compatible") {
      return {
        skip: serverSteps(ui, actions, (model) => async () => ({
          done: [message("setup.serverSaved", { model })],
        })),
      };
    }
    if (!isHosted(chosen)) return BACK;
    const key: Step = async () => {
      const saved = await askKey(ui, actions, chosen);
      if (saved === BACK) return BACK;
      if (saved === "empty") return { skip: key };
      const said =
        chosen === "tauric"
          ? message("setup.tauricSaved")
          : message("setup.connected", { provider: PROVIDER_LABELS[chosen] });
      return { done: [said, ...envWins(chosen)] };
    };
    return key;
  };
  return run(provider);
}

export function modelFlow(ui: FormUI, facts: SetupFacts, actions: SetupActions): Promise<string[]> {
  const { current } = facts;
  // What is known, with the keys saved on the way.
  const known: SetupFacts = { ...facts, keyFrom: { ...facts.keyFrom } };
  const saved =
    (model: string): Step =>
    async () => ({
      done: [
        message("setup.modelSaved", { model }),
        // A model named outside the config file comes first at every start.
        ...(facts.modelNamedBy ? [message("setup.modelNamedElsewhere", { where: facts.modelNamedBy })] : []),
      ],
    });
  /** Connect `provider` in place (its sign-in, server or key), then its models. */
  const connect =
    (provider: ProviderId): Step =>
    async () => {
      const models = modelSteps(ui, known, actions, provider, saved);
      if (isReady(known, provider)) return { skip: models };
      if (provider === "chatgpt") {
        if (!actions.signIn) return { done: [message("setup.signInElsewhere", { app: APP_NAME })] };
        return (await actions.signIn()) ? { skip: models } : BACK;
      }
      // A server's model is the one given with its address, saved with it.
      if (provider === "openai-compatible") return { skip: serverSteps(ui, actions, saved) };
      if (!isHosted(provider)) return BACK;
      const key: Step = async () => {
        const given = await askKey(ui, actions, provider);
        if (given === "saved") known.keyFrom[provider] = "stored";
        return given === BACK ? BACK : given === "empty" ? { skip: key } : models;
      };
      return { skip: key };
    };
  const provider: Step = async () => {
    const chosen = await ui.pick({
      title: message("setup.chooseProvider"),
      options: providerOptions(known, "model"),
      // The flow's first step: Esc ends it. Eight providers: typing finds one.
      filter: true,
      esc: "close",
      ...(current ? { start: current.provider } : {}),
    });
    if (chosen === BACK) return BACK;
    return connect(chosen as ProviderId);
  };
  return run(provider);
}
