// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Which model a run starts on, decided once: the one given on the command line; else, resuming, the
 * session's own (with its key found now); else the configured one; else, with none named, the one usable
 * provider's default. A route is usable when it resolved (a key found), its provider runs in this version
 * and, for a ChatGPT plan, its sign-in is there. With nothing usable an interactive run opens the setup
 * (also to replace a configured model that cannot be used); a headless run, or a model the setup cannot
 * change (a flag, the environment), stops and says why.
 */
import { CONFIG_FILE, ENV, type Settings } from "../config/index.js";
import { APP_NAME, HOSTED_PROVIDERS, message, type ProviderId, type RouteName } from "../contracts/index.js";
import { defaultModel, defaultOf } from "../engine/index.js";

export type StartupDeps = {
  /** The settings with this model and reasoning, as a flag would give them. */
  load(flags: { model?: string; reasoning?: string }): Promise<Settings>;
  /** Whether the ChatGPT sign-in is there and may use the plan (a local read). */
  signedIn(): Promise<boolean>;
  /** The route the session being resumed last ran on, if any. */
  savedRoute(): Promise<RouteName | undefined>;
};

export type Startup =
  /** `route`: the resumed session's own, when that is what it runs on. */
  | { kind: "ready"; settings: Settings; notices: string[]; route?: RouteName }
  | { kind: "setup"; settings: Settings; notices: string[] }
  | { kind: "stop"; settings: Settings; notices: string[]; reason: string };

export async function resolveStartup(
  flags: { model?: string; reasoning?: string },
  deps: StartupDeps,
  { interactive }: { interactive: boolean },
): Promise<Startup> {
  const base = await deps.load(flags);
  const label = (route: { provider: string; model: string }) => `${route.provider}/${route.model}`;
  // Why the settings' model cannot be used, or undefined when it can.
  const unusable = async (settings: Settings, before: Settings = base) => {
    const { model } = settings;
    if (!model)
      return (
        settings.problems.find((problem) => !before.problems.includes(problem)) ?? settings.problems[0] ?? ""
      );
    if (model.provider === "chatgpt" && !(await deps.signedIn()))
      return message("session.signedOut", { app: APP_NAME });
    return undefined;
  };
  const stop = (settings: Settings, reason: string, notices: string[] = []): Startup => ({
    kind: "stop",
    settings,
    notices,
    reason,
  });

  if (flags.model !== undefined) {
    const why = await unusable(base, { ...base, problems: [] });
    return why === undefined ? { kind: "ready", settings: base, notices: [] } : stop(base, why);
  }

  // A resumed session runs on its own route when it still can; else it is said, with what is used instead.
  const ran = await deps.savedRoute();
  let moved: { was: string; reason: string } | undefined;
  if (ran) {
    const reasoning = flags.reasoning ?? ran.reasoning;
    const onIt = await deps.load({ model: label(ran), ...(reasoning ? { reasoning } : {}) });
    const why = await unusable(onIt);
    if (why === undefined) return { kind: "ready", settings: onIt, notices: [], route: ran };
    moved = { was: label(ran), reason: why };
  }
  const movedNotice = (settings: Settings) =>
    moved
      ? [
          message("session.routeUnusable", {
            ...moved,
            ...(settings.model ? { now: label(settings.model) } : {}),
          }),
        ]
      : [];

  if (base.namedBy !== undefined) {
    const why = await unusable(base, { ...base, problems: [] });
    if (why === undefined) return { kind: "ready", settings: base, notices: movedNotice(base) };
    // The setup can replace what the config file names, not what the environment does.
    if (interactive && base.namedBy === CONFIG_FILE)
      return { kind: "setup", settings: base, notices: movedNotice(base) };
    return stop(base, why, movedNotice(base));
  }

  const signedIn = await deps.signedIn();
  const pick = defaultModel([...(signedIn ? (["chatgpt"] as const) : []), ...base.connected]);
  if ("model" in pick) {
    const chosen = await deps.load({ ...flags, model: pick.model });
    return { kind: "ready", settings: chosen, notices: movedNotice(chosen) };
  }
  if (interactive) return { kind: "setup", settings: base, notices: movedNotice(base) };
  const reason =
    pick.choices.length > 1
      ? message("cli.chooseModel", {
          providers: pick.choices.join(", "),
          example: defaultOf(pick.choices[0] as ProviderId) ?? "",
        })
      : setupHelp();
  return stop(base, reason, movedNotice(base));
}

/** Every way to set a model, for a run with no terminal to set one up in. */
export function setupHelp(): string {
  return message("cli.setup", {
    app: APP_NAME,
    baseUrlVar: ENV.baseURL,
    modelVar: ENV.model,
    providers: HOSTED_PROVIDERS.filter((provider) => provider !== "tauric"),
  });
}
