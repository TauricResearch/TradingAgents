// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The user's limits: config.json `limits` and `--limit` flags, read into `Limits` over the defaults
 * field by field.
 */
import { z } from "zod";
import { message } from "../contracts/index.js";
import { AGENT_NAME_PATTERN, DEFAULT_LIMITS, type Limits } from "../contracts/limits.js";

/** A duration as people write it: "90s", "15m", "2h", or a number of seconds. */
const duration = z
  .union([
    z.number().positive(),
    z.string().regex(/^\d+(\.\d+)?\s*(s|m|h)$/, 'a duration such as "90s", "15m" or "2h"'),
  ])
  .transform((value) =>
    Math.round(
      typeof value === "number"
        ? value * 1_000
        : Number.parseFloat(value) *
            { s: 1_000, m: 60_000, h: 3_600_000 }[value.trim().slice(-1) as "s" | "m" | "h"],
    ),
  )
  // A timer holds at most about 24 days.
  .refine((ms) => ms >= 1 && ms <= 2_147_483_647, "between a millisecond and 24 days");
const count = z.number().int().positive();
/** How a run's limits are written: steps and tokens are counts, time a duration. */
const RUN_FIELDS = { steps: count, tokens: count, time: duration } as const;
const OUTPUT_FIELDS = { stepTokens: count, finalTokens: count } as const;

/** The `limits` settings as written in config.json (and as `--limit` flags name them). */
export type LimitsSettings = {
  question?: { steps?: number; tokens?: number; time?: number | string };
  agents?: Record<string, { steps?: number; tokens?: number; time?: number | string }>;
  subagentsPerQuestion?: number;
  output?: { stepTokens?: number; finalTokens?: number };
  modelStall?: number | string;
};

/**
 * The limits from layers of settings, later ones over earlier ones field by field. Each setting is
 * checked on its own: one that cannot be used is named by its key and left at what it was, and the
 * others in its layer still apply.
 */
export function resolveLimits(...layers: unknown[]): { limits: Limits; problems: string[] } {
  const limits: Limits = structuredClone(DEFAULT_LIMITS);
  const problems: string[] = [];
  const record = (value: unknown): value is Record<string, unknown> =>
    typeof value === "object" && value !== null && !Array.isArray(value);
  /** A run's fields (`question`, an agent), each checked alone, into `target`. */
  const run = (
    path: string,
    value: unknown,
    target: { steps?: number; tokens?: number; timeMs?: number },
  ) => {
    if (!record(value)) return problems.push(message("limits.notSettings", { path }));
    for (const [field, raw] of Object.entries(value)) {
      const schema = Object.hasOwn(RUN_FIELDS, field)
        ? RUN_FIELDS[field as keyof typeof RUN_FIELDS]
        : undefined;
      if (!schema) {
        problems.push(message("limits.notALimit", { path: `${path}.${field}` }));
        continue;
      }
      const parsed = schema.safeParse(raw);
      if (!parsed.success)
        problems.push(message("limits.invalid", { path: `${path}.${field}`, reason: issue(parsed.error) }));
      else if (field === "time") target.timeMs = parsed.data;
      else target[field as "steps" | "tokens"] = parsed.data;
    }
  };
  for (const layer of layers) {
    if (layer === undefined) continue;
    if (!record(layer)) {
      problems.push('limits: settings by name, such as { "question": { "time": "20m" } }');
      continue;
    }
    for (const [key, value] of Object.entries(layer)) {
      if (key === "question") run("question", value, limits.question);
      else if (key === "agents") {
        if (!record(value)) {
          problems.push(message("limits.byAgent"));
          continue;
        }
        for (const [name, own] of Object.entries(value)) {
          // The main agent's limits are the question's.
          if (name === "main") problems.push(message("limits.mainUnderQuestion"));
          else if (!AGENT_NAME_PATTERN.test(name)) problems.push(message("limits.notAnAgent", { name }));
          else {
            const target = { ...limits.agents[name] };
            limits.agents[name] = target;
            run(`agents.${name}`, own, target);
          }
        }
      } else if (key === "subagentsPerQuestion") {
        const parsed = count.safeParse(value);
        if (parsed.success) limits.subagentsPerQuestion = parsed.data;
        else
          problems.push(
            message("limits.invalid", { path: "subagentsPerQuestion", reason: issue(parsed.error) }),
          );
      } else if (key === "output") {
        if (!record(value)) {
          problems.push('limits.output: settings such as { "stepTokens": 32768 }');
          continue;
        }
        for (const [field, raw] of Object.entries(value)) {
          const schema = Object.hasOwn(OUTPUT_FIELDS, field)
            ? OUTPUT_FIELDS[field as keyof typeof OUTPUT_FIELDS]
            : undefined;
          const parsed = schema?.safeParse(raw);
          if (!parsed) problems.push(message("limits.notAnOutputLimit", { field }));
          else if (!parsed.success)
            problems.push(
              message("limits.invalid", { path: `output.${field}`, reason: issue(parsed.error) }),
            );
          else limits.output[field as keyof typeof OUTPUT_FIELDS] = parsed.data;
        }
      } else if (key === "modelStall") {
        const parsed = duration.safeParse(value);
        if (parsed.success) limits.modelStallMs = parsed.data;
        else problems.push(message("limits.invalid", { path: "modelStall", reason: issue(parsed.error) }));
      } else
        problems.push(
          `limits.${key}: not a limit (question, agents, subagentsPerQuestion, output or modelStall)`,
        );
    }
  }
  return { limits, problems };
}

/**
 * `--limit` flags ("question.time=20m", "agents.news.steps=6") as a settings layer. A value that reads
 * as a number is one; anything else is kept as written (durations).
 */
export function limitFlags(flags: readonly string[]): { layer: Record<string, unknown>; problems: string[] } {
  const layer: Record<string, unknown> = {};
  const problems: string[] = [];
  for (const flag of flags) {
    const match = /^([a-zA-Z][\w.-]*)=(.+)$/.exec(flag.trim());
    if (!match) {
      problems.push(message("limits.flagShape", { flag }));
      continue;
    }
    const [, path, raw] = match as unknown as [string, string, string];
    const keys = path.split(".");
    // Only names a setting can have: never the object machinery.
    if (keys.some((key) => ["__proto__", "constructor", "prototype"].includes(key))) {
      problems.push(message("limits.flagUnknown", { flag }));
      continue;
    }
    let node = layer;
    for (const key of keys.slice(0, -1)) {
      const next = Object.hasOwn(node, key) ? node[key] : undefined;
      node[key] = typeof next === "object" && next !== null ? next : {};
      node = node[key] as Record<string, unknown>;
    }
    node[keys.at(-1) as string] = /^\d+(\.\d+)?$/.test(raw) ? Number(raw) : raw;
  }
  return { layer, problems };
}

/** What a settings schema says first about a value it refuses. */
function issue(error: z.ZodError): string {
  return error.issues[0]?.message ?? "not valid";
}
