// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Skill files as the Agent Skills standard writes them (agentskills.io/specification): a directory
 * `<name>/SKILL.md` whose YAML frontmatter holds `name`, `description` and optional `license`,
 * `compatibility`, `metadata` and `allowed-tools`, followed by Markdown. Files under `references/` and
 * `assets/` go with the skill and are read on demand; `scripts/` are not run (there is no shell).
 *
 * The built-in skills are held to the standard strictly. A user's skill, possibly written for another
 * client, is read leniently, as the standard's client guide asks: a departure from the rules is a
 * warning, and only frontmatter that cannot be read, or a missing description, keeps it out.
 */
import { parse } from "yaml";

export type SkillFile = {
  name: string;
  description: string;
  body: string;
  /** The standard's `metadata` (the built-in skills' `group` places them in the README's figure). */
  metadata?: Record<string, string>;
  /** Its bundled text files by path under the skill's directory (`references/…`, `assets/…`). */
  files: string[];
  /** The bundled files' text, for a skill compiled in; a user's are read from its directory. */
  resources?: Record<string, string>;
};

/** The directories whose files go with a skill and can be read with it. */
export const RESOURCE_DIRS = ["references", "assets"] as const;

const NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const FIELDS = new Set(["name", "description", "license", "compatibility", "metadata", "allowed-tools"]);

class SkillFileError extends Error {
  override readonly name = "SkillFileError";
}

/**
 * A skill from its SKILL.md text, the name of its directory, and its bundled files. `strict`: any
 * departure from the standard is an error (the built-in skills); otherwise it is a warning, and only
 * unreadable frontmatter or a missing description is an error.
 */
export function parseSkill(
  file: string,
  text: string,
  options: { dir: string; files?: string[]; resources?: Record<string, string>; strict: boolean },
): { skill: SkillFile; warnings: string[] } {
  const { frontmatter, body } = split(file, text);
  const fields = readYaml(file, frontmatter);
  const warnings: string[] = [];
  const warn = (problem: string) => {
    if (options.strict) throw new SkillFileError(`${file}: ${problem}`);
    warnings.push(problem);
  };
  const field = (key: string): string | undefined => {
    const value = fields[key];
    if (value === undefined || value === null) return undefined;
    if (typeof value === "string") return value.trim();
    warn(`${key} is not text`);
    return typeof value === "number" || typeof value === "boolean" ? String(value) : undefined;
  };
  const description = field("description");
  if (!description) throw new SkillFileError(`${file}: has no description`);
  if (description.length > 1024) warn("description is longer than 1024 characters");
  const given = field("name");
  const name = given || options.dir;
  if (!given) warn("has no name; the directory's is used");
  if (name.length > 64 || !NAME.test(name)) {
    warn(`name "${name}" is not lowercase letters, digits and single hyphens of at most 64 characters`);
  }
  if (name !== options.dir) warn(`name "${name}" differs from its directory "${options.dir}"`);
  const compatibility = field("compatibility");
  if (compatibility && compatibility.length > 500) warn("compatibility is longer than 500 characters");
  for (const key of Object.keys(fields)) if (!FIELDS.has(key)) warn(`${key} is not a field of the standard`);
  const metadata = metadataOf(fields.metadata, warn);
  if (!body) warn("has no text after its frontmatter");
  return {
    skill: {
      name,
      description,
      body,
      ...(metadata ? { metadata } : {}),
      files: [...(options.files ?? [])].sort(),
      ...(options.resources ? { resources: options.resources } : {}),
    },
    warnings,
  };
}

function split(file: string, text: string): { frontmatter: string; body: string } {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  // Only an unindented --- closes the frontmatter: an indented one belongs to a YAML block.
  if (lines[0]?.trimEnd() !== "---") throw new SkillFileError(`${file}: must start with a --- line`);
  const end = lines.findIndex((line, index) => index > 0 && line.trimEnd() === "---");
  if (end < 0) throw new SkillFileError(`${file}: the frontmatter has no closing --- line`);
  return {
    frontmatter: lines.slice(1, end).join("\n"),
    body: lines
      .slice(end + 1)
      .join("\n")
      .trim(),
  };
}

/**
 * The frontmatter as a mapping. Frontmatter that YAML refuses only because a value holds an unquoted
 * colon (`description: Use it: when ...`), as hand-written files often do, is read again with such
 * values quoted.
 */
function readYaml(file: string, frontmatter: string): Record<string, unknown> {
  const attempt = (source: string): Record<string, unknown> | undefined => {
    try {
      const value: unknown = parse(source);
      if (value === null || value === undefined) return {};
      return typeof value === "object" && !Array.isArray(value)
        ? (value as Record<string, unknown>)
        : undefined;
    } catch {
      return undefined;
    }
  };
  const read = attempt(frontmatter) ?? attempt(quoteColons(frontmatter));
  if (!read) throw new SkillFileError(`${file}: its frontmatter is not readable YAML`);
  return read;
}

function quoteColons(frontmatter: string): string {
  return frontmatter
    .split("\n")
    .map((line) => {
      const match = /^([A-Za-z][\w-]*):\s+(.*:\s.*)$/.exec(line);
      if (!match || /^["'>|[{]/.test(match[2] as string)) return line;
      return `${match[1]}: ${JSON.stringify(match[2])}`;
    })
    .join("\n");
}

function metadataOf(value: unknown, warn: (problem: string) => void): Record<string, string> | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "object" || Array.isArray(value)) {
    warn("metadata is not a mapping of keys to text");
    return undefined;
  }
  const entries = Object.entries(value as Record<string, unknown>).filter(([key, item]) => {
    if (typeof item === "string") return true;
    warn(`metadata.${key} is not text`);
    return typeof item === "number" || typeof item === "boolean";
  });
  return entries.length ? Object.fromEntries(entries.map(([key, item]) => [key, String(item)])) : undefined;
}
