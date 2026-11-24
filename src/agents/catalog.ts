// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The agents and skills a session may offer. Agents: the built-in ones, then the user's from the home
 * directory (`agents/<name>.md`). Skills, by precedence: the home directory's (`skills/<name>/SKILL.md`),
 * then those shared between agent clients (`~/.agents/skills`), then the built-in ones. One of a name
 * shadows the others, with a notice saying so. A user file that cannot be used is skipped with a notice
 * that names it and why; the built-in files are checked when they are compiled in.
 */
import type { Dirent } from "node:fs";
import { readdir, readFile, stat } from "node:fs/promises";
import { basename, dirname, join } from "node:path";
import { errorText, message } from "../contracts/index.js";
import { type AgentFile, parseAgentFile } from "./agent-file.js";
import { BUILTIN_AGENTS, BUILTIN_SKILLS } from "./builtin.generated.js";
import { listSkillFiles } from "./skill-dir.js";
import { parseSkill, type SkillFile } from "./skill-file.js";

/** Where a built-in agent or skill comes from, as `/agents` and `/skills` show it. */
export const BUILT_IN = "built-in";

/** An agent or skill with where it comes from: built-in, or the user file's path. */
export type CatalogEntry<T> = T & { source: string };

export type Catalog = {
  agents: CatalogEntry<AgentFile>[];
  skills: CatalogEntry<SkillFile>[];
  /** What was skipped or will not be used, one line each. */
  notices: string[];
};

export function builtinCatalog(): Catalog {
  return {
    agents: BUILTIN_AGENTS.map((agent) => ({ ...agent, source: BUILT_IN })),
    skills: BUILTIN_SKILLS.map((skill) => ({ ...skill, source: BUILT_IN })),
    notices: [],
  };
}

/**
 * The built-in agents and skills with the user's: the agent files in `agents` and the skills in
 * `skills`, over the skills in `shared` (`~/.agents/skills`). `tools`: every tool an agent may name; a
 * user agent naming another, a pattern matching none, or a skill there is not, is skipped.
 */
export async function loadCatalog(
  dirs: { agents: string; skills: string; shared?: string },
  tools: readonly string[],
): Promise<Catalog> {
  const notices: string[] = [];
  const skip = (path: string, problem: string) =>
    notices.push(message("agentFiles.skipped", { path, problem }));
  const skillsIn = (root: string) =>
    userFiles(root, "dirs", skip, (path, text) => {
      const dir = dirname(path);
      const { skill, warnings } = parseSkill(path, text, {
        dir: basename(dir),
        files: listSkillFiles(dir),
        strict: false,
      });
      for (const warning of warnings) notices.push(message("agentFiles.warning", { path, problem: warning }));
      return skill;
    });
  const skills = layered(
    [
      builtinCatalog().skills,
      ...(dirs.shared ? [await skillsIn(dirs.shared)] : []),
      await skillsIn(dirs.skills),
    ],
    skip,
    notices,
  );
  const known = new Set(skills.map((skill) => skill.name));
  const agents = (
    await userFiles(dirs.agents, "files", skip, (path, text) => parseAgentFile(path, text))
  ).filter((agent) => {
    const problem =
      matchTools(agent.tools, tools).missing.map((tool) => `no tool matches ${tool}`)[0] ??
      agent.skills.filter((skill) => !known.has(skill)).map((skill) => `there is no skill ${skill}`)[0];
    if (problem) skip(agent.source, problem);
    else if (agent.model !== undefined)
      notices.push(message("agentFiles.modelReserved", { path: agent.source }));
    return !problem;
  });
  // A user's agent replaces a built-in one of its name, as /agents shows; skills say so, as their standard asks.
  return { agents: layered([builtinCatalog().agents, agents], skip), skills, notices };
}

/**
 * The tools `patterns` name among `names`, in the order of `names`, and the patterns that match none.
 * A pattern is a name, or one with `*` standing for any run of characters.
 */
export function matchTools(
  patterns: readonly string[],
  names: readonly string[],
): { tools: string[]; missing: string[] } {
  const tests = patterns.map((pattern) => ({
    pattern,
    test: new RegExp(`^${pattern.split("*").map(escapePattern).join(".*")}$`),
  }));
  return {
    tools: names.filter((name) => tests.some(({ test }) => test.test(name))),
    missing: tests.filter(({ test }) => !names.some((name) => test.test(name))).map(({ pattern }) => pattern),
  };
}

/** An agent's prompt with the recipes of the skills it lists. */
export function withSkills(agent: AgentFile, skills: readonly SkillFile[]): string {
  const recipes = agent.skills.flatMap((name) => {
    const skill = skills.find((item) => item.name === name);
    return skill ? [`Skill ${skill.name}:\n${skill.body}`] : [];
  });
  return [agent.prompt, ...recipes].join("\n\n");
}

/**
 * The items of `layers`, lowest precedence first, one per name: an item replaces one of its name from a
 * lower layer (said in `notices`, when given); a second item of one name in a layer is skipped.
 */
function layered<T extends { name: string; source: string }>(
  layers: readonly (readonly T[])[],
  skip: (path: string, problem: string) => void,
  notices?: string[],
): T[] {
  const byName = new Map<string, T>();
  for (const layer of layers) {
    const taken = new Map<string, string>();
    for (const item of layer) {
      const first = taken.get(item.name);
      if (first !== undefined) {
        skip(item.source, `${first} is named ${item.name} too`);
        continue;
      }
      taken.set(item.name, item.source);
      const shadowed = byName.get(item.name);
      if (shadowed && notices)
        notices.push(
          message("agentFiles.shadows", { path: item.source, name: item.name, other: shadowed.source }),
        );
      byName.set(item.name, item);
    }
  }
  return [...byName.values()];
}

/** The user's files of one kind under `root`, parsed, in path order; a missing directory has none. */
async function userFiles<T>(
  root: string,
  layout: "files" | "dirs",
  skip: (path: string, problem: string) => void,
  parse: (path: string, text: string) => T,
): Promise<CatalogEntry<T>[]> {
  let entries: Dirent[];
  try {
    entries = await readdir(root, { withFileTypes: true });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") skip(root, errorText(error));
    return [];
  }
  // A skill's directory may be a link to one, as clients that share skills install them.
  const isDir = async (entry: Dirent) =>
    entry.isDirectory() ||
    (entry.isSymbolicLink() &&
      (await stat(join(root, entry.name)).catch(() => undefined))?.isDirectory() === true);
  const kept = await Promise.all(
    entries.map(async (entry) =>
      (layout === "files" ? entry.isFile() && entry.name.endsWith(".md") : await isDir(entry))
        ? entry
        : undefined,
    ),
  );
  const paths = kept
    .filter((entry): entry is Dirent => entry !== undefined)
    .map((entry) => (layout === "files" ? join(root, entry.name) : join(root, entry.name, "SKILL.md")))
    .sort();
  const found: CatalogEntry<T>[] = [];
  for (const path of paths) {
    try {
      found.push({ ...parse(path, await readFile(path, "utf8")), source: path });
    } catch (error) {
      // The parser's message starts with the file (and line), which the notice names already.
      const problem = errorText(error);
      const at = problem.startsWith(path) ? /^:(\d+)?:? ?/.exec(problem.slice(path.length)) : null;
      skip(
        path,
        at ? `${at[1] ? `line ${at[1]}: ` : ""}${problem.slice(path.length + at[0].length)}` : problem,
      );
    }
  }
  return found;
}

function escapePattern(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
