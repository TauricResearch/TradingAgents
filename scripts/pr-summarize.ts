#!/usr/bin/env bun
/**
 * Summarize a cached PR review via LLM (OpenRouter → Gemini 2.5 Flash).
 *
 * Usage:
 *   bun scripts/pr-summarize.ts 8              # summarize PR #8
 *   bun scripts/pr-summarize.ts 8 --write      # prepend to pr-8.md
 *   bun scripts/pr-summarize.ts 8 --output pr-8-summary.md
 *
 * Requires: OPENROUTER_API_KEY env var
 */

import { existsSync } from "node:fs"
import { join } from "node:path"
import { llm } from "./lib/llm.ts"

const MODEL = "google/gemini-2.5-flash-lite-preview-09-2025"

// ── Types ───────────────────────────────────────────────────────────────────

interface PrIssue {
  severity: "🔴" | "🟡" | "📘"
  title: string
  files: string[]
  description: string
  actions: string[]
}

// ── Prompt ──────────────────────────────────────────────────────────────────

const SYSTEM_PROMPT = `You are a senior code reviewer. Read the following PR review document and extract all actionable issues.

For each issue, provide in JSON:
- severity: "🔴" (bug), "🟡" (warning), or "📘" (rule)
- title: short summary (max 10 words)
- files: array of file paths with line ranges if available
- description: one-paragraph explanation of the problem
- actions: array of concrete fix steps

Output ONLY a valid JSON array. No markdown, no prose, no code blocks. Example:
[
  {"severity":"🔴","title":"SQLite REAL not parsed","files":["src/lib/intel-compute.ts:78-85"],"description":"...","actions":["Add parseFloat() before arithmetic"]}
]`

// ── API call ────────────────────────────────────────────────────────────────

async function callLlm(prompt: string): Promise<string> {
  return llm(
    [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: prompt },
    ],
    {
      model: MODEL,
      temperature: 0.2,
      maxTokens: 4000,
      title: "TradingAgents PR Summarizer",
      referer: "https://github.com/pjsvis/TradingAgents",
    },
  )
}

// ── Markdown generation ───────────────────────────────────────────────────

function toChecklist(issues: PrIssue[]): string {
  const lines: string[] = []
  lines.push("# PR Review Checklist (LLM-generated)")
  lines.push("")

  for (let i = 0; i < issues.length; i++) {
    const issue = issues[i]
    lines.push(`## ${issue.severity} Issue ${i + 1}: ${issue.title}`)
    lines.push("")
    lines.push(`**Severity:** ${issue.severity}`)
    lines.push(`**Files:** ${issue.files.join(", ")}`)
    lines.push("")
    lines.push(issue.description)
    lines.push("")
    lines.push("**Actions:**")
    for (const action of issue.actions) {
      lines.push(`- [ ] ${action}`)
    }
    lines.push("")
  }

  lines.push(`---`)
  lines.push(`_Generated ${new Date().toISOString()} via ${MODEL}_`)
  lines.push("")

  return lines.join("\n")
}

// ── Main ────────────────────────────────────────────────────────────────────

async function main() {
  const args = Bun.argv.slice(2)
  const num = args.find((a) => /^\d+$/.test(a))
  const writeMode = args.includes("--write")
  const outputArg = args.find((_, i) => args[i - 1] === "--output")

  if (!num) {
    console.error("Usage: bun scripts/pr-summarize.ts <pr-number> [--write] [--output file.md]")
    process.exit(1)
  }

  const prFile = join(process.cwd(), "debriefs", "reviews", `pr-${num}.md`)
  if (!existsSync(prFile)) {
    console.error(`Review not cached: ${prFile}`)
    console.error(`Run: just pr-fetch ${num}`)
    process.exit(1)
  }

  const reviewText = await Bun.file(prFile).text()
  if (reviewText.length < 200) {
    console.error("Review too short — nothing to summarize")
    process.exit(1)
  }

  // Truncate to ~8K chars to keep token count reasonable
  const truncated = reviewText.slice(0, 8000)

  console.error(`Summarizing PR #${num} (${truncated.length} chars)...`)
  const raw = await callLlm(truncated)

  let issues: PrIssue[]
  try {
    issues = JSON.parse(raw) as PrIssue[]
  } catch {
    console.error("LLM did not return valid JSON. Raw output:")
    console.error(raw)
    process.exit(1)
  }

  const checklist = toChecklist(issues)

  if (writeMode) {
    const outFile = prFile
    const existing = await Bun.file(outFile).text()
    const combined = `${checklist}\n\n${existing}`
    await Bun.write(outFile, combined)
    console.log(`Prepended checklist to ${outFile}`)
  } else if (outputArg) {
    const outFile = join(process.cwd(), "debriefs", "reviews", outputArg)
    await Bun.write(outFile, checklist)
    console.log(`Wrote: ${outFile}`)
  } else {
    console.log(checklist)
  }
}

main().catch((e) => {
  console.error("Error:", e.message)
  process.exit(1)
})
