// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** Reading the settings files: JSON parsed without throwing, and fields checked one by one. */
import type { z } from "zod";

/** The parsed text, or a value no reader takes for settings when it is not JSON. */
export function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return Symbol("not JSON");
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The fields of `source` that pass their schema; each one that fails is named in `problems`. */
export function pick(
  source: Record<string, unknown>,
  fields: Record<string, z.ZodType>,
  problem: (field: string) => string,
  problems: string[],
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [name, schema] of Object.entries(fields)) {
    if (source[name] === undefined) continue;
    const parsed = schema.safeParse(source[name]);
    if (parsed.success) out[name] = parsed.data;
    else problems.push(problem(name));
  }
  return out;
}
