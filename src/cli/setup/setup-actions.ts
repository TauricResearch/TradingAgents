// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** What a setup does on this computer: the config writers, and the ChatGPT sign-in where it can run. */
import {
  CONFIG_FILE,
  type CredentialName,
  type Paths,
  type Settings,
  saveCredential,
  saveModel,
  saveServer,
} from "../../config/index.js";
import { errorText, message, type RouteName } from "../../contracts/index.js";
import { chatgptAuth } from "../../engine/index.js";
import { homePath } from "../output.js";
import { hiddenLines } from "../secret.js";
import type { SetupActions, SetupFacts } from "./setup-flows.js";

/** What a setup knows from the settings, and whether the ChatGPT sign-in is there. */
export function setupFacts(settings: Settings, signedIn: boolean, current?: RouteName): SetupFacts {
  return {
    signedIn,
    keyFrom: settings.keyFrom,
    connected: settings.connected,
    ...(settings.choice?.provider === "openai-compatible" ? { serverModel: settings.choice.model } : {}),
    ...(current ? { current } : {}),
    ...(settings.namedBy && settings.namedBy !== CONFIG_FILE ? { modelNamedBy: settings.namedBy } : {}),
  };
}

export function setupActions({
  paths,
  say,
  added,
  terminal,
}: {
  /** Where the settings and the ChatGPT sign-in's file are. */
  paths: Paths;
  /** Lines for the person (never a value). */
  say: (line: string) => void;
  /** Told of each key as it is saved, so what runs now keeps it out of what it says and sends. */
  added?: (key: string) => void;
  /** Where the ChatGPT sign-in can run: a terminal no render holds. Without it there is no sign-in. */
  terminal?: { stdin: NodeJS.ReadStream; stdout: NodeJS.WriteStream };
}): SetupActions {
  const auth = chatgptAuth(paths.chatgptAuth);
  return {
    async saveKey(name: CredentialName, key) {
      const value = key.take();
      added?.(value);
      let path: string;
      try {
        path = await saveCredential(name, value, paths);
      } catch (error) {
        // Said without the key, whatever the failure's own text holds.
        throw new Error(message("setup.keyNotSaved", { reason: errorText(error).replaceAll(value, "***") }));
      }
      say(message("cli.keyStored", { name, path: homePath(path) }));
    },
    async saveServer(server, key) {
      const value = key?.take();
      if (value) added?.(value);
      await saveServer(server, value, paths);
    },
    async saveModel(choice) {
      await saveModel(choice, paths);
    },
    planModels: async () => (await auth.models()).map(({ id, name }) => ({ id, name })),
    ...(terminal
      ? {
          async signIn() {
            const stop = new AbortController();
            // A pasted address is read without being shown; Ctrl+C there, or a SIGINT, stops the sign-in.
            const reader = hiddenLines("", terminal.stdin, terminal.stdout, () => stop.abort());
            const onSignal = () => stop.abort();
            process.on("SIGINT", onSignal);
            try {
              const email = await auth.signIn({ say, pasted: reader.lines, signal: stop.signal });
              // Stopped after the browser had finished: the setup goes back as for any stop.
              if (stop.signal.aborted) return false;
              say(message("setup.signedInAs", { email }));
              return true;
            } catch (error) {
              say(errorText(error));
              return false;
            } finally {
              reader.close();
              process.off("SIGINT", onSignal);
            }
          },
        }
      : {}),
  };
}
