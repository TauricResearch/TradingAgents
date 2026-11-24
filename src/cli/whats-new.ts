// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * What's new: once per version, one line from the new version's notes (its first item, the rest a
 * command away), at the start of an interactive session. A fresh install says nothing and only
 * remembers its version.
 */
import { promises as fs } from "node:fs";
import { dirname } from "node:path";
import semver from "semver";
import { writeAtomic } from "../config/index.js";
import { message } from "../contracts/index.js";

/**
 * One version's notes from CHANGELOG.md: its sections in order, each a group's heading (none for the
 * version's own items, which come first) and its items. The first item is the version's highlight.
 */
export type VersionNotes = { version: string; sections: { heading?: string; items: string[] }[] };

export async function whatsNew({
  version,
  statePath,
  notes,
}: {
  version: string;
  statePath: string;
  notes: readonly VersionNotes[];
}): Promise<string | undefined> {
  const seen = await lastSeen(statePath);
  // Only a newer version is news; an older one started again leaves the newest seen as it is.
  const newer = seen === undefined || !semver.valid(seen) || semver.gt(version, seen);
  if (!newer) return undefined;
  await remember(statePath, version).catch(() => {});
  const current = notes.find((entry) => entry.version === version);
  const item = current?.sections[0]?.items[0];
  if (seen === undefined || !item) return undefined;
  return message("app.whatsNew", { version, item });
}

/**
 * The welcome's line of news, when it has one to show: with a Tauric key, what's new in this version (once,
 * and not for a resumed session), else a newer release (`updateNotice`). Without a key the welcome's slot says
 * where to get one, so nothing is read or recorded: a version's line counts as seen only once it is shown.
 */
export async function welcomeNews({
  keyed,
  resumed,
  updateNotice,
  ...seen
}: {
  keyed: boolean;
  resumed: boolean;
  updateNotice: string | undefined;
  version: string;
  statePath: string;
  notes: readonly VersionNotes[];
}): Promise<string | undefined> {
  if (!keyed) return undefined;
  return (resumed ? undefined : await whatsNew(seen)) ?? updateNotice;
}

/** The version last started, or undefined when none was (or the state cannot be read). */
async function lastSeen(path: string): Promise<string | undefined> {
  try {
    const state: unknown = JSON.parse(await fs.readFile(path, "utf8"));
    const value = (state as { lastSeenVersion?: unknown })?.lastSeenVersion;
    return typeof value === "string" ? value : undefined;
  } catch {
    return undefined;
  }
}

/** Written whole, in one step. */
async function remember(path: string, version: string): Promise<void> {
  await fs.mkdir(dirname(path), { recursive: true });
  await writeAtomic(path, `${JSON.stringify({ lastSeenVersion: version })}\n`);
}
