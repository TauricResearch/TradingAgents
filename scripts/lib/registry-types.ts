/**
 * Shared Zod schemas for all registries and the conceptual lexicon.
 */

import { z } from "zod"

// ── Registry entry schema — used by briefs, debriefs, decisions, playbooks, docs ──

export const RegistryEntrySchema = z.object({
  file: z.string(),
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "date must be YYYY-MM-DD"),
  status: z.enum(["open", "done", "active", "closed", "wontfix"]),
  summary: z.string(),
  meta: z.record(z.unknown()).optional().default({}),
})

export type RegistryEntry = z.infer<typeof RegistryEntrySchema>

// ── Conceptual lexicon schema ──

export const ConceptEntrySchema = z.object({
  slug: z.string().min(1),
  term: z.string().min(1),
  type: z.enum(["concept", "operational-heuristic", "anti-pattern", "principle", "pattern"]),
  heuristic: z.string(),
  usage: z.string(),
  coined_by: z.string().optional(),
  status: z.enum(["active", "deprecated", "draft"]).default("active"),
})

export type ConceptEntry = z.infer<typeof ConceptEntrySchema>

// ── Registry definitions ──

export const REGISTRIES = {
  briefs: { indexPath: "briefs/INDEX.jsonl", dirPath: "briefs" },
  debriefs: { indexPath: "debriefs/INDEX.jsonl", dirPath: "debriefs" },
  decisions: { indexPath: "decisions/INDEX.jsonl", dirPath: "decisions" },
  playbooks: { indexPath: "playbooks/REGISTRY.jsonl", dirPath: "playbooks" },
  docs: { indexPath: "docs/INDEX.jsonl", dirPath: "docs" },
} as const

export type RegistryName = keyof typeof REGISTRIES

export const REGISTRY_NAMES = Object.keys(REGISTRIES) as RegistryName[]

// ── Zod validation helpers ──

export function parseIndexFile(content: string): unknown[] {
  const lines = content.trim().split("\n").filter((l) => l.trim())
  return lines.map((line) => JSON.parse(line))
}

export function validateEntries<T>(
  entries: unknown[],
  schema: z.ZodSchema<T>,
): { valid: T[]; errors: Array<{ line: number; error: string }> } {
  const valid: T[] = []
  const errors: Array<{ line: number; error: string }> = []

  for (let i = 0; i < entries.length; i++) {
    const result = schema.safeParse(entries[i])
    if (result.success) {
      valid.push(result.data)
    } else {
      errors.push({ line: i + 1, error: result.error.message })
    }
  }

  return { valid, errors }
}

// ── File existence check ──

export function entryFileExists(registry: RegistryName, filename: string): boolean {
  const { readdirSync } = require("node:fs")
  const { join } = require("node:path")
  const dir = REGISTRIES[registry]?.dirPath
  if (!dir) return false
  try {
    return readdirSync(dir).includes(filename)
  } catch {
    return false
  }
}