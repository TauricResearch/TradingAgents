// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** The product's identity, read by every layer. */

/** The command people run; it names the home directory and prefixes the environment variables. */
export const APP_NAME = "tradingagents";
/** The product's name as people read it (the header). */
export const APP_TITLE = "TradingAgents";
/** Who makes it. */
export const MAKER = "Tauric Research";

/** This build's version; a test keeps it equal to package.json's. */
export const VERSION = "1.0.1";

/** How this build names itself to the services it calls. */
export const USER_AGENT = `${APP_NAME}/${VERSION}`;
