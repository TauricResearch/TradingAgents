#!/usr/bin/env bun
/**
 * Incorporate 7 CTX operational heuristics into silo-conceptual-lexicon.jsonl.
 *
 * These 7 terms from docs/conceptual-lexicon-example.json are directly
 * relevant to silo/project conventions. This script adds:
 *   - meta.heuristic:  concise actionable rule
 *   - meta.usage:      example sentence
 *   - meta.coined_by: (already present from conversion)
 *   - meta.origin:    updated to include CTX source ID
 *   - meta.tags:       updated with [Related: ...] to existing silo terms
 *
 * Run: bun scripts/ctx-lexicon-incorporate.ts
 */

import { readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"

const SILO_LEXICON = join(process.cwd(), "silo-conceptual-lexicon.jsonl")

// Entries to incorporate: id in CTX lexicon → (heuristic, usage, related silos terms)
const INCORPORATIONS: Record<
  string,
  { heuristic: string; usage: string; related: string[]; extraTags: string[] }
> = {
  "OH-040": {
    heuristic:
      "One concern per commit. If a change touches N directories, break it into N commits.",
    usage:
      "The refactor required touching 5 files across 3 directories. I factored it into 3 separate PRs.",
    related: ["extract-before-move", "fail-fast"],
    extraTags: [
      "[Origin: CTX OH-040]",
      "[Related: extract-before-move]",
      "[Related: fail-fast]",
      "[Related: conceptual-entropy]",
    ],
  },
  "OH-041": {
    heuristic: "The justfile is a facade, not a workbench. Complex logic lives in scripts.",
    usage:
      "Instead of inlining the complex build logic in the justfile, I extracted it to scripts/build.ts.",
    related: ["facade", "lab-first"],
    extraTags: [
      "[Origin: CTX OH-041]",
      "[Related: facade]",
      "[Related: lab-first]",
      "[Related: silo]",
    ],
  },
  "OH-082": {
    heuristic:
      "Use fast (pattern-matching) for trivial edits. Deliberate analysis for complex changes. If unsure, slow down.",
    usage:
      "The merge conflict looked simple, but I switched to slow thinking and found the real problem.",
    related: ["fail-fast", "lab-first"],
    extraTags: [
      "[Origin: CTX OH-082]",
      "[Related: fail-fast]",
      "[Related: lab-first]",
      "[Related: impartial-spectator]",
    ],
  },
  "OH-092": {
    heuristic:
      "Validate data before building UI. Run scripts in the lab before wiring to the dashboard.",
    usage:
      "Before building the portfolio chart, I validated the price data with scripts/get_price.ts.",
    related: ["lab-first", "console-first-validation", "live-data-principle"],
    extraTags: [
      "[Origin: CTX OH-092]",
      "[Related: lab-first]",
      "[Related: console-first-validation]",
      "[Related: live-data-principle]",
    ],
  },
  "OH-095": {
    heuristic: "Test the idea. Automate the process. Scale the system. Evangelize the pattern.",
    usage:
      "The alert system passed all tests, so I automated it with a just recipe and documented it in playbooks/.",
    related: ["one-shot-port", "tase-mandate"],
    extraTags: [
      "[Origin: CTX OH-095]",
      "[Related: one-shot-port]",
      "[Related: tase-mandate]",
      "[Related: silo]",
    ],
  },
  "OH-130": {
    heuristic: "When debugging performance, check data volume before code logic.",
    usage:
      "The dashboard was slow. Before profiling, I checked the SQLite DB size and archive count.",
    related: ["data-first-diagnostics", "fail-fast"],
    extraTags: [
      "[Origin: CTX OH-130]",
      "[Related: data-first-diagnostics]",
      "[Related: fail-fast]",
      "[Related: barnacle]",
    ],
  },
  "OH-131": {
    heuristic:
      "Separate the workbench from the filing cabinet. Explore in scripts/lab/ before touching production.",
    usage:
      "I tested the new chart renderer in scripts/lab/chart-test.ts before moving it to src/server/views/.",
    related: ["lab-first", "exploratory-programming"],
    extraTags: [
      "[Origin: CTX OH-131]",
      "[Related: lab-first]",
      "[Related: exploratory-programming]",
      "[Related: entropy-sink]",
    ],
  },
}

interface LexiconEntry {
  file: string
  id: string
  date: string
  status: string
  type: string
  summary: string
  meta: {
    category?: string
    heuristic?: string
    usage?: string
    tags?: string[]
    coined_by?: string
    related?: string[]
    origin?: string
  }
}

interface SiloEntry {
  file: string
  id: string
  date: string
  status: string
  type: string
  summary: string
  meta: {
    category?: string
    heuristic?: string
    usage?: string
    tags?: string[]
    coined_by?: string
    related?: string[]
    origin?: string
  }
}

function loadSiloEntries(): SiloEntry[] {
  const content = readFileSync(SILO_LEXICON, "utf-8")
  return content
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as SiloEntry)
}

function saveSiloEntries(entries: SiloEntry[]): void {
  const output = `${entries.map((e) => JSON.stringify(e)).join("\n")}\n`
  writeFileSync(SILO_LEXICON, output, "utf-8")
}

function incorporate(): void {
  const entries = loadSiloEntries()
  let added = 0
  let updated = 0

  for (const [ctxId, data] of Object.entries(INCORPORATIONS)) {
    const existing = entries.find((e) => e.id === ctxId)

    if (existing) {
      // Update existing entry with heuristic + usage + tags
      existing.meta ??= {}
      existing.meta.heuristic = data.heuristic
      existing.meta.usage = data.usage
      existing.meta.origin = `CTX ${ctxId} — incorporated into silo`
      existing.meta.related = data.related
      // Merge extra tags (avoid duplicates)
      const existingTags = new Set(existing.meta.tags ?? [])
      for (const tag of data.extraTags) {
        if (!existingTags.has(tag)) {
          existing.meta.tags = [...(existing.meta.tags ?? []), tag]
          existingTags.add(tag)
        }
      }
      updated++
      console.log(`  ✓ updated ${ctxId}: ${existing.file}`)
    } else {
      // Load from CTX lexicon and add to silo
      const ctxRaw = readFileSync(join(process.cwd(), "debriefs/lexicon-ctx.jsonl"), "utf-8")
      const ctxEntries = ctxRaw
        .trim()
        .split("\n")
        .map((l) => JSON.parse(l) as LexiconEntry)
      const ctxEntry = ctxEntries.find((e) => e.id === ctxId)
      if (!ctxEntry) {
        console.log(`  ✗ ${ctxId}: not found in CTX lexicon either`)
        return
      }
      const newEntry: SiloEntry = {
        file: ctxEntry.file,
        id: ctxEntry.id,
        date: new Date().toISOString().slice(0, 10),
        status: "active",
        type: ctxEntry.type,
        summary: ctxEntry.summary,
        meta: {
          category: ctxEntry.meta?.category,
          origin: `CTX ${ctxId} — incorporated into silo`,
          heuristic: data.heuristic,
          usage: data.usage,
          coined_by: ctxEntry.meta?.coined_by ?? "human",
          related: data.related,
          tags: [...(ctxEntry.meta?.tags ?? []), ...data.extraTags],
        },
      }
      entries.push(newEntry)
      added++
      console.log(`  + added ${ctxId}: ${ctxEntry.file}`)
    }
  }

  saveSiloEntries(entries)
  console.log(`\nIncorporated: ${added} added, ${updated} updated`)
  console.log(`  → ${SILO_LEXICON}`)
}

incorporate()
