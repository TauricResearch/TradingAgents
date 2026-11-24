// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Agent files: Markdown whose first lines, between `---` markers, hold a few settings, one
 * `key: value` per line (a list as `[a, b]`). The grammar is deliberately small and strict: an unknown
 * key, a repeated key or any other syntax is an error that names the file and line, never a guess.
 */

import { z } from "zod";
import { AGENT_FILE_STEPS, AGENT_NAME_PATTERN } from "../contracts/limits.js";

export type AgentFile = {
  name: string;
  /** What people see the agent called while it works ("Equity Research"). */
  label: string;
  description: string;
  tier: "deep" | "quick";
  /** Data tools by name, or by a pattern where `*` stands for any run of characters (`price_*`). */
  tools: string[];
  /** Skills whose recipes are added to the agent's prompt. */
  skills: string[];
  /** Reserved for a per-agent model; agents run on the session's model. */
  model?: string;
  steps: number;
  prompt: string;
};

const name = z.string().regex(AGENT_NAME_PATTERN, "lowercase letters, digits, - or _");

const agentFields = z
  .object({
    name,
    label: z.string().min(2).max(40),
    description: z.string().min(10).max(400),
    tier: z.enum(["deep", "quick"]).default("quick"),
    tools: z.array(z.string().regex(/^[a-z*][a-z0-9_*]*$/, "a tool name, or a pattern with *")).default([]),
    // Checked against the skills there are, whose names follow their own standard.
    skills: z.array(z.string().min(1).max(64)).default([]),
    model: z.string().min(1).max(100).optional(),
    steps: z
      .string()
      .regex(/^\d+$/, "a whole number")
      .transform(Number)
      .pipe(z.number().int().min(1).max(AGENT_FILE_STEPS.max))
      .default(AGENT_FILE_STEPS.default),
  })
  .strict();

class AgentFileError extends Error {
  override readonly name = "AgentFileError";
}

/** The settings and body of an agent file. */
function split(file: string, text: string): { fields: Record<string, string | string[]>; body: string } {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  if (lines[0] !== "---") throw new AgentFileError(`${file}: must start with a --- line`);
  const end = lines.indexOf("---", 1);
  if (end < 0) throw new AgentFileError(`${file}: the settings have no closing --- line`);
  const fields: Record<string, string | string[]> = {};
  for (let index = 1; index < end; index++) {
    const line = lines[index] as string;
    if (!line.trim()) continue;
    const match = /^([a-z_]+): (.+)$/.exec(line);
    if (!match) throw new AgentFileError(`${file}:${index + 1}: expected "key: value"`);
    const [, key = "", raw = ""] = match;
    if (key in fields) throw new AgentFileError(`${file}:${index + 1}: ${key} is set twice`);
    const value = raw.trim();
    if (/^\[.*\]$/.test(value)) {
      const inner = value.slice(1, -1).trim();
      const items = inner ? inner.split(",").map((item) => item.trim()) : [];
      if (items.some((item) => !item))
        throw new AgentFileError(`${file}:${index + 1}: ${key} has an empty item`);
      fields[key] = items;
    } else fields[key] = value;
  }
  const body = lines
    .slice(end + 1)
    .join("\n")
    .trim();
  if (!body) throw new AgentFileError(`${file}: has no text after its settings`);
  return { fields, body };
}

function problem(file: string, error: z.ZodError): AgentFileError {
  return new AgentFileError(
    `${file}: ${error.issues.map((issue) => `${issue.path.join(".") || "settings"}: ${issue.message}`).join("; ")}`,
  );
}

export function parseAgentFile(file: string, text: string): AgentFile {
  const { fields, body } = split(file, text);
  const parsed = agentFields.safeParse(fields);
  if (!parsed.success) throw problem(file, parsed.error);
  const { model, ...settings } = parsed.data;
  return { ...settings, ...(model !== undefined ? { model } : {}), prompt: body };
}
