// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * A skill's bundled files on disk: the text files under its `references/` and `assets/`, by path
 * relative to the skill's directory, and reading one of them safely.
 */
import { closeSync, fstatSync, lstatSync, openSync, readdirSync, readSync, realpathSync } from "node:fs";
import { isAbsolute, join, normalize, relative, sep } from "node:path";
import { SKILL_FILE_BYTES } from "../contracts/limits.js";
import { RESOURCE_DIRS } from "./skill-file.js";

/** The longest path a skill's file is named by, as use_skill takes it. */
export const SKILL_PATH_CHARS = 200;

/** The text files under the skill's resource directories, within the size bound, sorted. */
export function listSkillFiles(dir: string): string[] {
  const found: string[] = [];
  const walk = (at: string) => {
    let entries: string[];
    try {
      entries = readdirSync(join(dir, at));
    } catch {
      return;
    }
    for (const entry of entries) {
      const path = join(at, entry);
      // Links are not followed: a skill's files are its own.
      const stat = lstatSync(join(dir, path));
      if (stat.isDirectory()) walk(path);
      else if (stat.isFile() && stat.size <= SKILL_FILE_BYTES) {
        const listed = path.split(sep).join("/");
        // Only a file use_skill can give back is offered: a path it takes, and text.
        if (listed.length <= SKILL_PATH_CHARS && readBounded(join(dir, path)) !== undefined)
          found.push(listed);
      }
    }
  };
  for (const root of RESOURCE_DIRS) walk(root);
  return found.sort();
}

/**
 * One of a skill's listed files, read from its directory; undefined unless `file` is one of `listed`,
 * stays inside the directory once links are resolved, and is text within the size bound.
 */
export function readSkillFile(dir: string, listed: readonly string[], file: string): string | undefined {
  const wanted = normalize(file).split(sep).join("/");
  if (isAbsolute(file) || wanted.startsWith("../") || !listed.includes(wanted)) return undefined;
  try {
    const root = realpathSync(dir);
    const path = realpathSync(join(dir, wanted));
    const inside = relative(root, path);
    if (!inside || inside.startsWith("..") || isAbsolute(inside)) return undefined;
    return readBounded(path);
  } catch {
    return undefined;
  }
}

/** A regular file's text, read no further than the size bound; undefined when over it, or not text. */
function readBounded(path: string): string | undefined {
  const fd = openSync(path, "r");
  try {
    if (!fstatSync(fd).isFile()) return undefined;
    const buffer = Buffer.alloc(SKILL_FILE_BYTES + 1);
    let length = 0;
    for (;;) {
      const read = readSync(fd, buffer, length, buffer.length - length, null);
      if (read === 0) break;
      length += read;
      if (length > SKILL_FILE_BYTES) return undefined;
    }
    const bytes = buffer.subarray(0, length);
    return bytes.includes(0) ? undefined : bytes.toString("utf8");
  } finally {
    closeSync(fd);
  }
}

/** Every listed file's text, for a skill compiled into the executable. */
export function readSkillFiles(dir: string, listed: readonly string[]): Record<string, string> {
  return Object.fromEntries(
    listed.flatMap((file) => {
      const text = readSkillFile(dir, listed, file);
      return text === undefined ? [] : [[file, text]];
    }),
  );
}
