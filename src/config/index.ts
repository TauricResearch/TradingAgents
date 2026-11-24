// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Everything a user or the environment sets, and where it lives: the home directory and its files
 * (paths), environment variables (env), config.json (settings), stored keys (credentials), the user's
 * limits (limits) and where releases come from (release).
 */

// Files replaced whole, for what the command line writes (exports, its own state).
export { writeAtomic } from "../store/index.js";
export { CREDENTIAL_NAMES, type CredentialName } from "./credentials.js";
export { ENV, envName, KEY_VARS } from "./env.js";
export {
  addToHistory,
  HISTORY_KEPT,
  loadHistory,
  saveHistory,
  withQuestion,
} from "./history.js";
export { type LimitsSettings, limitFlags, resolveLimits } from "./limits.js";
export {
  CONFIG_FILE,
  HISTORY_FILE,
  homeDir,
  MEMORY_DIR,
  type Paths,
  resolvePaths,
  SESSIONS_DIR,
} from "./paths.js";
export {
  INSTALL_COMMAND,
  NPM_PACKAGE,
  NPM_PLATFORM_PREFIX,
  NPM_UPDATE_COMMAND,
  RELEASE_URL,
  REPOSITORY_URL,
} from "./release.js";
export {
  checkEndpoint,
  loadSettings,
  type Settings,
  saveCredential,
  saveModel,
  saveServer,
  saveSync,
} from "./settings.js";
