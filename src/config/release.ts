// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Where releases come from and how they are installed: the public repository, its latest release,
 * the installer, and the npm packages. The npm launcher (scripts/npm/launcher.js) is shipped as written
 * and repeats its names; a test keeps them equal to these.
 */
import { APP_NAME } from "../contracts/index.js";

/** The public repository. */
export const REPOSITORY_URL = "https://github.com/TauricResearch/TradingAgents";

/** Where a newer release is looked up: the release the public repository marks latest. */
export const RELEASE_URL = "https://api.github.com/repos/TauricResearch/TradingAgents/releases/latest";

/** How to install a release from scratch. */
export const INSTALL_COMMAND = "curl -fsSL https://tauric.ai/tradingagents/install.sh | sh";

/** The npm package people install, and the start of each platform's package name (`<prefix><os>-<cpu>`). */
export const NPM_PACKAGE = `@tauric/${APP_NAME}`;
export const NPM_PLATFORM_PREFIX = `${NPM_PACKAGE}-`;
/** The command that installs or updates the npm package. */
export const NPM_UPDATE_COMMAND = `npm i -g ${NPM_PACKAGE}`;
