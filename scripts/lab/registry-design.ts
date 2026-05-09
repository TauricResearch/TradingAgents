#!/usr/bin/env bun
/**
 * Lab: Playbook Registry Design
 *
 * Explores what a proper canonical playbook registry looks like.
 * What exists now vs what we need.
 *
 * Run: bun scripts/lab/registry-design.ts
 */

import { readFileSync } from "node:fs"
import { join } from "node:path"

// ── Current state ────────────────────────────────────────────────────────────

interface CurrentRegistryEntry {
  file: string
  date: string
  status: "canonical" | "project" | "active"
  summary: string
  meta: {
    source?: string | null
    mining_candidate?: boolean
    mining_note?: string | null
    last_mined?: string | null
  }
}

function loadCurrentRegistry(): CurrentRegistryEntry[] {
  const raw = readFileSync("playbooks/REGISTRY.jsonl", "utf-8")
  return raw
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line))
}

// ── Analyze current registry ───────────────────────────────────────────────

function analyzeCurrent() {
  const entries = loadCurrentRegistry()

  const canonical = entries.filter((e) => e.status === "canonical")
  const project = entries.filter((e) => e.status === "project" || e.status === "active")
  const miningCandidates = entries.filter((e) => e.meta.mining_candidate === true)
  const neverMined = miningCandidates.filter((e) => !e.meta.last_mined)

  console.log("=== CURRENT REGISTRY STATE ===")
  console.log("")
  console.log(`Total playbooks:     ${entries.length}`)
  console.log(`  Canonical:         ${canonical.length}`)
  console.log(`  Project-specific:  ${project.length}`)
  console.log(`Mining candidates:   ${miningCandidates.length}`)
  console.log(`  Never mined:       ${neverMined.length}`)
  console.log("")

  console.log("=== CANONICAL PLAYBOOKS ===")
  for (const e of canonical) {
    console.log(`  ${e.file.padEnd(30)} ${e.summary.slice(0, 50)}`)
  }
  console.log("")

  console.log("=== MINING CANDIDATES (never mined) ===")
  for (const e of neverMined) {
    console.log(`  ${e.file.padEnd(30)} ${e.meta.mining_note?.slice(0, 50) ?? ""}`)
  }
  console.log("")

  // What's missing?
  console.log("=== GAPS IN CURRENT SYSTEM ===")
  console.log("")
  console.log("1. NO EXTRACTION MECHANISM")
  console.log("   'mining_candidate' is a boolean flag, not an action.")
  console.log("   No script exists to strip project-specific content and")
  console.log("   produce a clean canonical playbook for reuse.")
  console.log("")
  console.log("2. NO IMPORT MECHANISM")
  console.log("   Starting a new project? You manually copy playbooks.")
  console.log("   No 'reg import canonical-playbook' command.")
  console.log("")
  console.log("3. NO SCRIPT REGISTRY")
  console.log("   scripts/ has no index. Reusable scripts (reg-check.ts,")
  console.log("   reg-sync.ts, gum.ts) are discoverable only by ls.")
  console.log("")
  console.log("4. NO LESSON-LEARNED FEEDBACK LOOP")
  console.log("   When a project playbook proves its worth, there's no path")
  console.log("   to promote it to canonical except manual editing.")
  console.log("")
  console.log("5. NO EXTERNAL REGISTRY")
  console.log("   Canonical playbooks are inside this repo. They can't be")
  console.log("   shared across projects without git submodules or copying.")
  console.log("")
}

// ── Proposed registry structure ────────────────────────────────────────────

function showProposed() {
  console.log("=== PROPOSED: CANONICAL REGISTRY ===")
  console.log("")
  console.log("A separate directory or repo that holds only canonical patterns:")
  console.log("")
  console.log("  canonicals/")
  console.log("    playbooks/          # Reusable playbooks (stripped of project detail)")
  console.log("    scripts/            # Reusable scripts (with project-agnostic interfaces)")
  console.log("    templates/          # Project scaffolding templates")
  console.log("    INDEX.jsonl         # Canonical registry index")
  console.log("    README.md           # How to adopt, how to contribute back")
  console.log("")
  console.log("Commands:")
  console.log("")
  console.log("  bun scripts/reg-mine.ts <playbook>")
  console.log("    → Strips project-specific content, outputs to canonicals/playbooks/")
  console.log("")
  console.log("  bun scripts/reg-import.ts <canonical-playbook>")
  console.log("    → Pulls a canonical playbook into current project's playbooks/")
  console.log("    → Marks it as 'canonical' in local REGISTRY.jsonl")
  console.log("")
  console.log("  bun scripts/reg-promote.ts <project-playbook>")
  console.log("    → Submits a proven project playbook for canonical consideration")
  console.log("    → Creates a diff showing what would be stripped")
  console.log("")
  console.log("  bun scripts/reg-list-canonicals.ts")
  console.log("    → Lists all canonical playbooks available for import")
  console.log("")
  console.log("  bun scripts/reg-sync-scripts.ts")
  console.log("    → Indexes scripts/ directory, marks reusable ones")
  console.log("")
}

// ── Main ─────────────────────────────────────────────────────────────────

analyzeCurrent()
showProposed()
