// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Where the user's settings and data live: the home directory, named after the product, and the
 * entries at its top. Inside `sessions/` and `memory/`, files are named by the code that keeps them.
 */

import { homedir } from "node:os";
import { isAbsolute, join } from "node:path";
import { APP_NAME, message } from "../contracts/index.js";
import { ENV } from "./env.js";

/** The settings file. */
export const CONFIG_FILE = "config.json";
/** The private file stored keys are kept in. */
const CREDENTIALS_FILE = "credentials.json";
/** The private file a ChatGPT sign-in is kept in, beside the credentials. */
const CHATGPT_AUTH_FILE = "chatgpt-auth.json";
/** The questions asked in the terminal. */
export const HISTORY_FILE = "history.jsonl";
/** What the last check for a newer release found. */
const UPDATE_STATE_FILE = "update-check.json";
/** What the app keeps between starts (the version whose news was shown). */
const STATE_FILE = "state.json";
/** The lock `update` holds while it replaces the executable. */
const UPDATE_LOCK_FILE = "update.lock";
/** The directories of saved sessions, of memory, and of the user's own agents and skills. */
export const SESSIONS_DIR = "sessions";
export const MEMORY_DIR = "memory";
const AGENTS_DIR = "agents";
const SKILLS_DIR = "skills";

/**
 * Where the user's settings, keys, own agents and skills, sessions and memory live: `<APP>_HOME`
 * (must be absolute), else `~/.tauric/<app>`.
 */
export function homeDir(env: NodeJS.ProcessEnv = process.env): string {
  const explicit = env[ENV.home];
  if (explicit !== undefined) {
    if (!isAbsolute(explicit)) throw new Error(message("config.homeNotAbsolute", { variable: ENV.home }));
    return explicit;
  }
  return join(homedir(), ".tauric", APP_NAME);
}

/** The skills shared by agent apps on this computer (`~/.agents/skills`), read beside the user's own. */
function sharedSkillsDir(): string {
  return join(homedir(), ".agents", "skills");
}

/** The home directory and the entries at its top the app reads and writes, resolved once per run. */
export type Paths = {
  home: string;
  config: string;
  credentials: string;
  chatgptAuth: string;
  history: string;
  updateCheck: string;
  state: string;
  updateLock: string;
  agents: string;
  skills: string;
  /** The skills shared by agent apps on this computer. */
  sharedSkills: string;
};

/** Where everything is, for the home directory `env` names (see `homeDir`, which may throw). */
export function resolvePaths(env: NodeJS.ProcessEnv = process.env): Paths {
  const home = homeDir(env);
  return {
    home,
    config: join(home, CONFIG_FILE),
    credentials: join(home, CREDENTIALS_FILE),
    chatgptAuth: join(home, CHATGPT_AUTH_FILE),
    history: join(home, HISTORY_FILE),
    updateCheck: join(home, UPDATE_STATE_FILE),
    state: join(home, STATE_FILE),
    updateLock: join(home, UPDATE_LOCK_FILE),
    agents: join(home, AGENTS_DIR),
    skills: join(home, SKILLS_DIR),
    sharedSkills: sharedSkillsDir(),
  };
}
