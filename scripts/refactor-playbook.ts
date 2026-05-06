#!/usr/bin/env bun
/**
 * Refactor a playbook markdown file from "war story" to clean playbook format.
 *
 * Usage:
 *   bun scripts/refactor-playbook.ts playbooks/htmx-playbook.md --write
 */

import { existsSync } from "node:fs"
import { llm } from "./lib/llm.ts"

const MODEL = "google/gemini-2.5-flash-lite-preview-09-2025"

// ── System prompt ─────────────────────────────────────────────────────────

const SYSTEM_PROMPT = `You are a technical documentation editor. Your job is to refactor a "war story" style playbook into a clean, prescriptive, actionable playbook.

Rules:
1. REMOVE all narrative about past mistakes, migrations, bans, and historical context (e.g. "This was a mistake", "Why we banned X", "Previously we did Y", "The fix:", "What happened:").
2. REMOVE all references to specific file refactor dates, line counts of removed code, or historical file states.
3. KEEP all technical rules, patterns, and constraints. Preserve every substantive technical instruction.
4. REPHRASE each remaining rule as a direct imperative: "Do X", "Never do Y", "Always Z".
5. STRUCTURE the output as a proper playbook with:
   - YAML frontmatter (date, tags: [playbook, htmx, hono, typescript])
   - H1 title
   - One-sentence Purpose
   - Prerequisites / Context
   - Standards & Patterns (the rules, grouped logically)
   - Quick Reference table
   - Validation / How to verify compliance
6. Maintain all code examples, but strip the "❌ Previously broken / ✅ Fixed" framing. Just show the correct pattern. If a wrong pattern is genuinely useful as a warning, show it briefly in an "Anti-Patterns" section with a one-line rationale — no historical narrative.
7. Preserve the "Banned Patterns" table but reframe it as "Forbidden Patterns" with the rationale being architectural, not historical.
8. The tone should be authoritative and concise — "this is how we do it", not "here's what we learned".

Output ONLY the refactored markdown. No preamble, no meta-commentary.`

// ── API call ──────────────────────────────────────────────────────────────

async function callLlm(system: string, user: string): Promise<string> {
  return llm(
    [
      { role: "system", content: system },
      { role: "user", content: user },
    ],
    {
      model: MODEL,
      temperature: 0.3,
      maxTokens: 8000,
      title: "TradingAgents Playbook Refactor",
      referer: "https://github.com/pjsvis/TradingAgents",
    },
  )
}

// ── Main ────────────────────────────────────────────────────────────────────

async function main() {
  const args = Bun.argv.slice(2)
  const filePath = args.find((a) => !a.startsWith("--"))
  const writeMode = args.includes("--write")

  if (!filePath) {
    console.error("Usage: bun scripts/refactor-playbook.ts <file.md> [--write]")
    process.exit(1)
  }

  if (!existsSync(filePath)) {
    console.error(`File not found: ${filePath}`)
    process.exit(1)
  }

  const content = await Bun.file(filePath).text()
  console.error(`Refactoring ${filePath} (${content.length} chars)...`)

  const refactored = await callLlm(SYSTEM_PROMPT, content)

  if (writeMode) {
    // Backup original
    const backup = `${filePath}.backup`
    await Bun.write(backup, content)
    await Bun.write(filePath, refactored)
    console.log(`Wrote refactored playbook to ${filePath}`)
    console.log(`Original backed up to ${backup}`)
  } else {
    console.log(refactored)
  }
}

main().catch((e) => {
  console.error("Error:", e.message)
  process.exit(1)
})
