// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** Links the app shows: the project's addresses, written as terminal hyperlinks. */
import { REPOSITORY_URL } from "../config/index.js";
import { SIGN_UP_URL } from "../contracts/index.js";

/** A link: what is shown, and where it goes. */
export type Link = { text: string; url: string };

export const REPO: Link = { text: REPOSITORY_URL.replace(/^https:\/\//, ""), url: REPOSITORY_URL };
export const SITE: Link = { text: "tauric.ai", url: "https://tauric.ai" };
/** Where to sign up for a Tauric API key, written as its whole address. */
export const SIGN_UP: Link = { text: SIGN_UP_URL, url: SIGN_UP_URL };

/**
 * `text` as an OSC 8 hyperlink to `url`. A terminal without hyperlinks ignores the sequence, as it does any
 * OSC string it does not know, and shows the text; the text is the address itself, so it reads either way.
 * Not on a terminal that takes only ASCII (likely too old for OSC strings).
 */
export function hyperlink(text: string, url: string, unicode: boolean): string {
  return unicode ? `\u001b]8;;${url}\u001b\\${text}\u001b]8;;\u001b\\` : text;
}
