#!/usr/bin/env node
// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The command line. Commands that need no model (help, version, key) run without settings;
 * a question needs a configured model. Only the interactive session mounts the terminal UI.
 */
import {
  limitFlags,
  loadSettings,
  type Paths,
  resolveLimits,
  resolvePaths,
  type Settings,
} from "../config/index.js";
import {
  APP_NAME,
  APP_TITLE,
  errorText,
  type ModelRoute,
  message,
  type RouteName,
  VERSION,
} from "../contracts/index.js";
import {
  agentLimitProblems,
  type Catalog,
  chatgptAuth,
  createEngine,
  dataToolNames,
  download,
  type EngineBuilder,
  isHere,
  listSessions,
  loadCatalog,
  modelReplayKey,
  resolveContextWindow,
  Session,
  SessionError,
  type SyncSetup,
  savedRoute,
  sendPendingDeletions,
  tauricSessions,
} from "../engine/index.js";
import { EXIT, runHeadless } from "../headless/run.js";
import { type Args, EXIT_USAGE, misuseOf, parse, USAGE } from "./args.js";
import type { ChatControls } from "./ChatApp.js";
import { FlowCancelledError } from "./form/form-ui.js";
import { openChat, type RunsOn } from "./interactive.js";
import { fitted, print, toErr, toOut } from "./output.js";
import { selfUpdate, updateWay } from "./self-update.js";
import { SessionHost } from "./session-host.js";
import { stepsUI } from "./setup/SetupSteps.js";
import { setupActions, setupFacts } from "./setup/setup-actions.js";
import { firstRun } from "./setup/setup-flows.js";
import { resolveStartup, type Startup, type StartupDeps, setupHelp } from "./startup.js";
import {
  deleteCommand,
  loginChatGPT,
  logoutChatGPT,
  sessions,
  storeKey,
  sync,
  update,
} from "./subcommands.js";
import { themeFrom } from "./theme.js";
import { offerUpdate, runOnTerminal } from "./update-prompt.js";
import { checkForUpdate, releaseLookup, skipVersion, updateSource } from "./updates.js";

/** Set when the app left a turn that would not stop: its timers and requests must not keep the process. */
let endNow = false;

async function main(argv: string[]): Promise<number> {
  let parsed: Args;
  try {
    parsed = parse(argv);
  } catch (error) {
    toErr(`${errorText(error)}\n\n${USAGE}\n`);
    return EXIT_USAGE;
  }
  const { values, positionals } = parsed;
  if (values.help) return print(USAGE);
  if (values.version) return print(VERSION);
  const [command, ...rest] = positionals;
  const misuse = misuseOf(command, rest, values);
  if (misuse) {
    toErr(`${misuse}\n\n${USAGE}\n`);
    return EXIT_USAGE;
  }

  // Everything below reads or writes the home directory, found once here: a home that cannot be named
  // stops the command, saying why.
  const paths = resolvePaths();
  if (command === "key") return storeKey(rest[0], paths);
  if (command === "sessions")
    return rest[0] === "delete"
      ? deleteCommand(rest[1], Boolean(values.yes), paths)
      : sessions(rest[0], paths);
  if (command === "sync") return sync(rest[0], paths);
  if (command === "update") return update(paths);
  if (command === "login") return loginChatGPT(rest[1], paths);
  if (command === "logout") return logoutChatGPT(paths);

  // Limits given on the command line come over config.json's, field by field.
  const flags = limitFlags(values.limit ?? []);
  // A limit given on the command line that cannot be used stops the run before it starts.
  const given = resolveLimits(flags.layer);
  // The user's agents and skills beside the built-in ones.
  const catalog: Catalog | undefined = await (async () => {
    try {
      return await loadCatalog(
        { agents: paths.agents, skills: paths.skills, shared: paths.sharedSkills },
        dataToolNames(),
      );
    } catch {
      return undefined;
    }
  })();
  const refused = [...flags.problems, ...given.problems, ...agentLimitProblems(given.limits, catalog)];
  if (refused.length) {
    toErr(`${refused.join("\n")}\n\n${USAGE}\n`);
    return EXIT_USAGE;
  }
  const headless = values.prompt !== undefined;
  if (!headless && (!process.stdin.isTTY || !process.stdout.isTTY)) {
    toErr(`${message("cli.needsTerminal", { app: APP_NAME })}\n`);
    return EXIT_USAGE;
  }
  const modelFlags = {
    ...(values.model !== undefined ? { model: values.model } : {}),
    ...(values.reasoning !== undefined ? { reasoning: values.reasoning } : {}),
  };
  // A resumed session runs on the model it ran on, unless one is given now; its key is the one found now.
  const resuming =
    values.resume ?? (values.continue ? (await listSessions(paths.home, { limit: 1 }))[0]?.id : undefined);
  // A session named that is only in the Tauric account is copied here first (sync on, with a key), so it
  // opens on its own route as any session here does.
  let copied = false;
  if (values.resume !== undefined && !(await isHere(paths.home, values.resume))) {
    const saved = await loadSettings(process.env, { paths });
    if (saved.sync && saved.tauricKey) {
      try {
        copied =
          (await download(paths.home, values.resume, tauricSessions(saved.tauricKey))) === "downloaded";
      } catch (error) {
        toErr(
          `${error instanceof SessionError ? error.message : message("sync.copyFailed", { reason: errorText(error) })}\n`,
        );
        return 1;
      }
    }
  }
  const startupDeps: StartupDeps = {
    load: (given) => loadSettings(process.env, { limits: flags.layer, flags: given, paths }),
    signedIn: () =>
      chatgptAuth(paths.chatgptAuth)
        .canUsePlan()
        .catch(() => false),
    savedRoute: async () =>
      resuming !== undefined && values.model === undefined ? savedRoute(paths.home, resuming) : undefined,
  };
  let startup = await resolveStartup(modelFlags, startupDeps, { interactive: !headless });
  // Nothing usable: the setup, then the same choice again with what it saved.
  if (startup.kind === "setup") {
    if (!(await firstRunSetup(startup.settings, startupDeps, paths))) return EXIT.cancelled;
    startup = await resolveStartup(modelFlags, startupDeps, { interactive: !headless });
  }
  const settings = startup.settings;
  // The route the session runs on, as the choice read it: checked again once the session is held.
  const ran = startup.kind === "ready" ? startup.route : undefined;
  // Those left are config.json's: the command line's were refused above.
  for (const problem of [
    ...settings.problems,
    ...agentLimitProblems(settings.limits, catalog),
    ...startup.notices,
    ...(catalog?.notices ?? []),
  ])
    toErr(`${message("cli.warning", { problem })}\n`);
  if (startup.kind === "stop") {
    toErr(`${startup.reason.trimEnd()}\n`);
    return EXIT_USAGE;
  }
  if (startup.kind === "setup" || !settings.model) {
    toErr(setupHelp());
    return EXIT_USAGE;
  }

  // A newer release is told from what an earlier start found; the look itself runs in the background. A
  // copy that can be updated from here is asked whether to update now; any other is told in the news line.
  const ending = new AbortController();
  const source = headless ? undefined : updateSource();
  const known = source
    ? checkForUpdate({
        source,
        current: VERSION,
        statePath: paths.updateCheck,
        now: Date.now,
        signal: ending.signal,
        upgradeCommand: `${APP_NAME} update`,
      })
    : undefined;
  const way = known?.available ? updateWay(process.execPath) : undefined;
  let updateNotice = known?.notice;
  if (source && known?.available && way) {
    updateNotice = undefined;
    const ui = stepsUI(themeFrom(process.env));
    const onSignal = () => ui.cancel();
    process.on("SIGINT", onSignal);
    let outcome: "exit" | "continue";
    try {
      outcome = await offerUpdate({
        ui,
        latest: known.available,
        current: VERSION,
        way,
        close: () => ui.close(),
        selfUpdate: () =>
          selfUpdate({
            execPath: process.execPath,
            current: VERSION,
            lookup: releaseLookup(),
            lockPath: paths.updateLock,
          }),
        run: runOnTerminal,
        skip: (version) => skipVersion(paths.updateCheck, source.url, version),
        out: toOut,
        err: toErr,
      });
    } catch (error) {
      if (!(error instanceof FlowCancelledError)) throw error;
      ending.abort();
      return EXIT.cancelled;
    } finally {
      ui.close();
      process.off("SIGINT", onSignal);
    }
    if (outcome === "exit") {
      ending.abort();
      return 0;
    }
  }

  // Every key found; one stored during the session (/login) joins it, so a model error never shows it either.
  const liveKeys = [...settings.keys];
  /** How a session on `model` is copied to the Tauric account of `key`, while sync stays on. */
  const syncTo = (key: string, model: ModelRoute): SyncSetup => ({
    remote: tauricSessions(key),
    metadata: { client: APP_NAME, version: VERSION, model: model.model },
    stillOn: async () => (await loadSettings(process.env, { paths })).sync,
  });
  /** What a session on `chosen`'s model runs with: its engine, its window, and where it is copied. */
  const runOn = async (chosen: Settings & { model: ModelRoute }): Promise<RunsOn> => {
    const { model } = chosen;
    const context = await resolveContextWindow(model, { chatgptAuthPath: paths.chatgptAuth });
    const build: EngineBuilder = (init) =>
      createEngine({
        model,
        limits: chosen.limits,
        ...(chosen.tauricKey ? { tauricKey: chosen.tauricKey } : {}),
        version: VERSION,
        contextWindow: context.window,
        modelLimits: {
          ...(context.input ? { input: context.input } : {}),
          ...(context.output ? { output: context.output } : {}),
        },
        dataDir: paths.home,
        chatgptAuthPath: paths.chatgptAuth,
        secrets: liveKeys,
        // A question the agent asks needs a person to answer it: none is there in a headless run.
        asks: !headless,
        ...(catalog ? { catalog } : {}),
        ...init,
      });
    // Sessions are copied to Tauric only when sync is on, and never without a Tauric key.
    const sync = chosen.sync && chosen.tauricKey ? syncTo(chosen.tauricKey, model) : undefined;
    return { model, context, build, sync };
  };
  const first = await runOn({ ...settings, model: settings.model });
  const { model, context, build, sync: syncSetup } = first;
  // A session is told once that its context window is assumed: when it starts, not each time it resumes.
  const resumed = values.resume !== undefined || Boolean(values.continue);
  const notices = context.notice && !resumed ? [context.notice] : [];
  // Problems found while the session runs go to the app once it is up, to stderr before and without it.
  const controls: ChatControls = {};
  const early: string[] = [];
  const report = (problem: string) =>
    headless
      ? toErr(`${message("cli.warning", { problem })}\n`)
      : controls.notice
        ? controls.notice(problem)
        : early.push(problem);
  if (settings.sync && !settings.tauricKey) report(message("sync.onWithoutKey"));
  // Said as what happened, not as a problem.
  if (copied) {
    if (headless) toErr(`${message("app.copiedFromAccount")}\n`);
    else early.push(message("app.copiedFromAccount"));
  }
  /**
   * What a session started or resumed in the chat runs on: chosen as at startup (this run's --model, else
   * the resumed session's own route, else the model saved for new sessions), with its problems said.
   */
  const runsOnChosen = async (chosen: Startup) => {
    for (const notice of chosen.notices) report(notice);
    if (chosen.kind !== "ready" || !chosen.settings.model) {
      throw new SessionError(chosen.kind === "stop" ? chosen.reason.trim() : message("app.noModelNow"));
    }
    return runOn({ ...chosen.settings, model: chosen.settings.model });
  };
  const chooseFor = async (resumeId?: string) =>
    runsOnChosen(
      await resolveStartup(
        modelFlags,
        { ...startupDeps, savedRoute: async () => (resumeId ? savedRoute(paths.home, resumeId) : undefined) },
        { interactive: false },
      ),
    );
  /**
   * What the open session runs on once switched to `route` in the chat (/model, a key saved): resolved
   * as at startup with that route named, so a route that cannot be used now is refused with why.
   */
  const chooseRoute = async (route: RouteName) =>
    runsOnChosen(
      await resolveStartup(
        {
          model: `${route.provider}/${route.model}`,
          ...(route.reasoning ? { reasoning: route.reasoning } : {}),
        },
        { ...startupDeps, savedRoute: async () => undefined },
        { interactive: false },
      ),
    );
  // Account deletions that could not be sent before go now, while the session runs.
  if (syncSetup) void sendPendingDeletions(paths.home, syncSetup.remote).catch(() => {});
  let session: Session;
  try {
    session = await openSession(
      paths.home,
      values,
      resuming,
      modelReplayKey(model),
      build,
      report,
      syncSetup,
    );
    // The route was read before the session was taken: a turn another run added since may have moved it.
    if (ran && resuming !== undefined && !sameRoute(await savedRoute(paths.home, resuming), ran)) {
      await session.close();
      throw new SessionError(message("session.changedWhileOpening"));
    }
  } catch (error) {
    if (!(error instanceof SessionError)) throw error;
    toErr(`${error.message}\n`);
    return 1;
  }

  // The chat's session, switched in place by /new and /resume; closed as whichever it is then.
  let host: SessionHost | undefined;
  try {
    if (headless) {
      for (const notice of notices) toErr(`${notice}\n`);
      // An interrupt or a termination stops the turn, which ends and is saved; a second one leaves at once.
      const stopping = new AbortController();
      const stop = (signal: NodeJS.Signals) => {
        if (stopping.signal.aborted) process.exit(signal === "SIGTERM" ? 143 : EXIT.cancelled);
        stopping.abort();
      };
      process.on("SIGINT", stop);
      process.on("SIGTERM", stop);
      try {
        const { code } = await runHeadless(session, values.prompt as string, {
          out: process.stdout,
          err: process.stderr,
          format: values.json ? "jsonl" : "answer",
          signal: stopping.signal,
        });
        return code;
      } finally {
        process.off("SIGINT", stop);
        process.off("SIGTERM", stop);
      }
    }
    host = new SessionHost(session);
    const unasked = settings.syncAsked ? undefined : settings.tauricKey;
    const chat = await openChat({
      host,
      paths,
      settings,
      runsOn: first,
      catalog,
      limits: flags.layer,
      signedIn: startupDeps.signedIn,
      liveKeys,
      chooseFor,
      chooseRoute,
      report,
      controls,
      notices,
      early,
      resumed,
      updateNotice: updateNotice,
      // Sync has no default: with a Tauric key, the app asks once (a headless run has no one to ask).
      syncOffer: unasked ? { setupFor: (model: ModelRoute) => syncTo(unasked, model) } : undefined,
    });
    // Ctrl+C at the keyboard reaches the app as input; a SIGINT sent from outside takes the same path.
    const onSignal = () => controls.interrupt?.();
    process.on("SIGINT", onSignal);
    try {
      await chat.exited;
    } finally {
      process.off("SIGINT", onSignal);
      ending.abort();
      await known?.refresh;
      await chat.kept();
    }
    // A session with something in it can be picked up again: say how, once the app has gone.
    const last = host.current;
    if (controls.asked || last.replay.events.length) {
      toOut(`${message("app.resumeHint", { app: APP_NAME, id: last.id })}\n`);
    }
    if (!controls.abandoned) return 0;
    endNow = true;
    return EXIT.cancelled;
  } finally {
    await (host ?? session).close();
  }
}

function sameRoute(a: RouteName | undefined, b: RouteName): boolean {
  return a?.provider === b.provider && a.model === b.model && a.reasoning === b.reasoning;
}

/** The first run's setup, step by step on this terminal; false when it was left before the end. */
async function firstRunSetup(settings: Settings, deps: StartupDeps, paths: Paths): Promise<boolean> {
  const ui = stepsUI(themeFrom(process.env));
  const onSignal = () => ui.cancel();
  process.on("SIGINT", onSignal);
  // Lines between the steps, broken between words to the window; a line's later rows under its indent.
  const columns = process.stdout.isTTY ? process.stdout.columns : undefined;
  toOut(`${fitted(message("setup.intro", { title: APP_TITLE }), columns)}\n\n`);
  const say = (line: string) => toOut(`${fitted(line, columns, 2)}\n`);
  try {
    await firstRun(
      ui,
      setupFacts(settings, await deps.signedIn()),
      setupActions({ paths, say, terminal: { stdin: process.stdin, stdout: process.stdout } }),
    );
    return true;
  } catch (error) {
    if (!(error instanceof FlowCancelledError)) throw error;
    toErr(`${message("setup.left", { app: APP_NAME })}\n`);
    return false;
  } finally {
    ui.close();
    process.off("SIGINT", onSignal);
  }
}

/** A new session, or the one named by --resume, or the latest with --continue. */
async function openSession(
  dir: string,
  values: { continue?: boolean; resume?: string },
  resuming: string | undefined,
  replayKey: string,
  build: EngineBuilder,
  report: (problem: string) => void,
  sync: SyncSetup | undefined,
): Promise<Session> {
  if (resuming !== undefined) return Session.resume(dir, resuming, replayKey, build, report, sync);
  if (values.continue) throw new SessionError(message("cli.noSessionToContinue"));
  return Session.start(dir, build, report, sync);
}

// A failure no command answers itself (a file that cannot be written, say) is said in one line.
process.exitCode = await main(process.argv.slice(2)).catch((error: unknown) => {
  const reason = errorText(error).replace(/\s+/g, " ").trim();
  toErr(`${message("cli.failed", { reason })}\n`);
  return 1;
});
// The session is closed by now; what the abandoned turn still holds open is not waited for.
if (endNow) process.exit();
