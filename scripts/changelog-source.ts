// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** CHANGELOG.md as data: each version's items, newest first, and the module the build bundles. */
import type { VersionNotes } from "../src/cli/whats-new.js";

/**
 * The versions in a changelog: each `## ` heading starts one (its version is the first thing on it, with
 * or without brackets), each `### ` heading under it a group of its notes, and each `- ` line an item of the
 * group it is in (items before any group are the version's own), continued by the indented lines after it.
 */
export function parseChangelog(text: string): VersionNotes[] {
  const versions: VersionNotes[] = [];
  for (const line of text.split(/\r?\n/)) {
    const heading = /^##\s+\[?v?([^\]\s]+)\]?/.exec(line);
    if (heading) {
      versions.push({ version: heading[1] as string, sections: [] });
      continue;
    }
    const current = versions.at(-1);
    if (!current) continue;
    const group = /^###\s+(.+)$/.exec(line);
    if (group) {
      current.sections.push({ heading: (group[1] as string).trim(), items: [] });
      continue;
    }
    const item = /^-\s+(.*)$/.exec(line);
    const section = current.sections.at(-1);
    if (item) {
      if (section) section.items.push((item[1] as string).trim());
      else current.sections.push({ items: [(item[1] as string).trim()] });
    } else if (/^\s+\S/.test(line) && section?.items.length) {
      section.items[section.items.length - 1] += ` ${line.trim()}`;
    }
  }
  return versions;
}

/** Version `version`'s section of a changelog as written, its heading left out; undefined when it has none. */
export function releaseNotes(text: string, version: string): string | undefined {
  const lines = text.split(/\r?\n/);
  const start = lines.findIndex((line) => /^##\s+\[?v?([^\]\s]+)\]?/.exec(line)?.[1] === version);
  if (start < 0) return undefined;
  const end = lines.findIndex((line, index) => index > start && /^##\s/.test(line));
  return lines
    .slice(start + 1, end < 0 ? undefined : end)
    .join("\n")
    .trim();
}

export function renderChangelog(versions: readonly VersionNotes[]): string {
  return [
    "// Copyright 2026 Tauric Research",
    "// SPDX-License-Identifier: Apache-2.0",
    "// Generated from CHANGELOG.md; do not edit.",
    'import type { VersionNotes } from "./whats-new.js";',
    "",
    `export const CHANGELOG: readonly VersionNotes[] = ${JSON.stringify(versions, null, 2)};`,
    "",
  ].join("\n");
}
