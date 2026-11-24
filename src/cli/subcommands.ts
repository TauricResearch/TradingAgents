// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The commands besides a question: login, logout, sync, sessions (and deleting one), key and update.
 * Each returns its exit code.
 */
import { createInterface } from "node:readline";
import {
  CREDENTIAL_NAMES,
  type CredentialName,
  ENV,
  KEY_VARS,
  loadSettings,
  type Paths,
  saveCredential,
  saveModel,
  saveSync,
} from "../config/index.js";
import { APP_NAME, errorText, type HostedProvider, message, VERSION } from "../contracts/index.js";
import { allSessions, chatgptAuth, deleteSession, SessionError, tauricSessions } from "../engine/index.js";
import { EXIT } from "../headless/run.js";
import { EXIT_USAGE, USAGE } from "./args.js";
import { homePath, print, toErr, toOut } from "./output.js";
import { hiddenLines, InputCancelledError, readHidden, readPiped } from "./secret.js";
import { selfUpdate, updateReport } from "./self-update.js";
import { releaseLookup } from "./updates.js";

/** Sign in with ChatGPT, then use the plan's model (the one named, or the plan's first). */
export async function loginChatGPT(wanted: string | undefined, paths: Paths): Promise<number> {
  const auth = chatgptAuth(paths.chatgptAuth);
  // A pasted address is read without being shown (it holds the sign-in's code); Ctrl+C stops the sign-in.
  const stop = new AbortController();
  const reader = process.stdin.isTTY
    ? hiddenLines("", process.stdin, process.stdout, () => stop.abort())
    : undefined;
  try {
    const email = await auth.signIn({
      say: (text) => toOut(`${text}\n`),
      signal: stop.signal,
      ...(reader ? { pasted: reader.lines } : {}),
    });
    const models = await auth.models();
    const chosen = wanted ? models.find((m) => m.id === wanted) : models[0];
    if (!chosen) {
      toErr(
        `${message("chatgpt.noModel", { email, ...(wanted ? { wanted } : {}), models: models.map((m) => m.id) })}\n`,
      );
      return 1;
    }
    const path = await saveModel({ provider: "chatgpt", model: chosen.id }, paths);
    return print(
      message("chatgpt.using", {
        email,
        name: chosen.name,
        id: chosen.id,
        path,
        models: models.map((m) => m.id),
        app: APP_NAME,
      }),
    );
  } catch (error) {
    toErr(`${errorText(error)}\n`);
    return stop.signal.aborted ? EXIT.cancelled : 1;
  } finally {
    reader?.close();
    process.stdin.pause();
  }
}

export async function logoutChatGPT(paths: Paths): Promise<number> {
  const result = await chatgptAuth(paths.chatgptAuth).signOut();
  if (result === undefined) return print(message("chatgpt.notSignedIn"));
  return print(message(result === "revoked" ? "chatgpt.signedOut" : "chatgpt.signedOutUnconfirmed"));
}

export async function sync(choice: string | undefined, paths: Paths): Promise<number> {
  if (choice === "on" || choice === "off") {
    const path = await saveSync(choice === "on", paths);
    const effective = (await loadSettings(process.env, { paths })).sync ? "on" : "off";
    if (effective !== choice) {
      return print(message("sync.setButOverridden", { choice, path, variable: ENV.sync, effective }));
    }
    return print(
      choice === "on"
        ? `${message("sync.isOn", { path })}\n\n${message("sync.sends")}`
        : message("sync.isOff", { path }),
    );
  }
  if (choice === "status" || choice === undefined) {
    const settings = await loadSettings(process.env, { paths });
    const state = !settings.syncAsked
      ? "unset"
      : settings.sync
        ? settings.tauricKey
          ? "on"
          : "onWithoutKey"
        : "off";
    return print(
      `${message("sync.status", { state })}\n\n${message("sync.sends")}\n\n${message("sync.turnItWith", { app: APP_NAME, to: settings.sync ? "off" : "on" })}`,
    );
  }
  toErr(`${message("sync.sayWhich", { app: APP_NAME })}\n\n${USAGE}\n`);
  return EXIT_USAGE;
}

/** Delete session `id`, here and (when sync is on) from the account; asks first at a terminal unless `yes`. */
export async function deleteCommand(id: string | undefined, yes: boolean, paths: Paths): Promise<number> {
  if (!id) {
    toErr(`${message("cli.nameTheSession", { app: APP_NAME })}\n`);
    return EXIT_USAGE;
  }
  const settings = await loadSettings(process.env, { paths });
  const remote = settings.sync && settings.tauricKey ? tauricSessions(settings.tauricKey) : undefined;
  if (!yes) {
    if (!process.stdin.isTTY) {
      toErr(`${message("cli.deleteNeedsYes")}\n`);
      return EXIT_USAGE;
    }
    const input = createInterface({ input: process.stdin, output: process.stdout });
    try {
      const asked = message(remote ? "cli.deleteEverywhere" : "cli.deleteHere", { id });
      const answer = await new Promise<string>((resolve) => input.question(`${asked} [y/N] `, resolve));
      if (!/^y(es)?$/i.test(answer.trim())) return print(message("cli.nothingDeleted"));
    } finally {
      input.close();
    }
  }
  try {
    const where = await deleteSession(paths.home, id, remote);
    return print(message(`app.deleted.${where}` as const));
  } catch (error) {
    if (!(error instanceof SessionError)) throw error;
    toErr(`${error.message}\n`);
    return 1;
  }
}

export async function sessions(extra: string | undefined, paths: Paths): Promise<number> {
  if (extra !== undefined) {
    toErr(`${message("cli.unexpectedArgument", { argument: extra })}\n\n${USAGE}\n`);
    return EXIT_USAGE;
  }
  const settings = await loadSettings(process.env, { paths });
  const remote = settings.sync && settings.tauricKey ? tauricSessions(settings.tauricKey) : undefined;
  const { sessions: listed, problem } = await allSessions(paths.home, remote);
  if (problem) toErr(`${message("cli.warning", { problem })}\n`);
  if (!listed.length) return print(message("cli.noSessions"));
  const lines = listed.map((s) => {
    const when = s.updated.toISOString().slice(0, 16).replace("T", " ");
    // One line, however the question was written.
    const words = [...s.title.replace(/\s+/g, " ").trim()];
    const title =
      words.length > 70
        ? `${words.slice(0, 69).join("")}…`
        : words.join("") || message(s.where === "account" ? "cli.untitledAccount" : "cli.untitledSession");
    return `${s.id}  ${when}  ${title}${s.where === "account" ? `  ${message("cli.inAccount")}` : ""}`;
  });
  return print(`${lines.join("\n")}\n\n${message("cli.continueOne", { app: APP_NAME })}`);
}

export async function storeKey(name: string | undefined, paths: Paths): Promise<number> {
  if (!(CREDENTIAL_NAMES as readonly (string | undefined)[]).includes(name)) {
    toErr(`${message("cli.nameTheKey", { app: APP_NAME, names: CREDENTIAL_NAMES.join(", ") })}\n`);
    return EXIT_USAGE;
  }
  let value: string;
  try {
    value = process.stdin.isTTY
      ? await readHidden(
          message("cli.keyPrompt", { name: name as CredentialName }),
          process.stdin,
          process.stdout,
        )
      : await readPiped(process.stdin);
  } catch (error) {
    toErr(`${message("cli.nothingStored")}\n`);
    return error instanceof InputCancelledError ? EXIT.cancelled : 1;
  }
  try {
    const path = await saveCredential(name as CredentialName, value, paths);
    print(message("cli.keyStored", { name: name as CredentialName, path: homePath(path) }));
    // A key in the environment comes first: storing one does not change what is used while it is set.
    const variables = name === "model" ? [ENV.modelKey] : KEY_VARS[name as HostedProvider];
    const variable = variables.find((candidate) => process.env[candidate]?.trim());
    return variable ? print(message("cli.envKeyWins", { variable })) : 0;
  } catch (error) {
    toErr(`${message("cli.nothingStoredBecause", { reason: errorText(error) })}\n`);
    return 1;
  }
}

/** Replace this executable with the newest release (see self-update.ts). */
export async function update(paths: Paths): Promise<number> {
  const report = await updateReport(() =>
    selfUpdate({
      execPath: process.execPath,
      current: VERSION,
      lookup: releaseLookup(),
      lockPath: paths.updateLock,
    }),
  );
  if (!report.failed) return print(report.text);
  toErr(`${report.text}\n`);
  return 1;
}
