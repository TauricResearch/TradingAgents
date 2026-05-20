#!/usr/bin/env bun
import { parseArgs } from "node:util"
/**
 * kpdf — Local Kreuzberg PDF wrapper
 *
 * Usage:
 *   bun kpdf.ts <verb> --file <path>
 *
 * Verbs:
 *   parse   — Extract PDF → markdown (default)
 *   index   — Extract PDF → JSON (structured nodes or content string)
 *   inspect — Show metadata + structure summary
 *   help    — Show this help
 *
 * Install: bun add @kreuzberg/node
 */
import { extractFileSync } from "@kreuzberg/node"

// ── Verb registry ──────────────────────────────────────────────────────────────

const VERBS = ["parse", "index", "inspect", "help"] as const
type Verb = (typeof VERBS)[number]

// ── Argument parser ─────────────────────────────────────────────────────────────

function parseArgsWithVerb() {
  return parseArgs({
    allowPositionals: true,
    options: {
      file: { type: "string", short: "f" },
      verb: { type: "string", short: "v" },
      help: { type: "boolean", short: "h", default: false },
    },
  })
}

function requireFile(path: string | undefined): asserts path is string {
  if (!path) {
    console.error("Error: --file <path> is required")
    process.exit(1)
  }
}

function requireVerb(v: string): asserts v is Verb {
  if (!VERBS.includes(v as Verb)) {
    console.error(`Error: unknown verb '${v}'. Use: ${VERBS.join(", ")}`)
    process.exit(1)
  }
}

// ── Extract helpers ─────────────────────────────────────────────────────────────

type ExtractionResult = {
  content: string
  metadata: {
    pageCount?: number
    createdAt?: string
    formatType?: string
    pdfVersion?: string
    isEncrypted?: boolean
    width?: number
    height?: number
  }
  elements: unknown[]
  qualityScore?: number
}

function extractJson(file: string): ExtractionResult {
  try {
    return extractFileSync(file, undefined, { outputFormat: "json" }) as ExtractionResult
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`Error reading ${file}: ${msg}`)
    process.exit(1)
  }
}

function extractMarkdown(file: string): { content: string } {
  try {
    return extractFileSync(file, undefined, { outputFormat: "markdown" })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`Error reading ${file}: ${msg}`)
    process.exit(1)
  }
}

// ── Verb: parse ────────────────────────────────────────────────────────────────

function verbParse(file: string) {
  const result = extractMarkdown(file)
  process.stdout.write(result.content)
}

// ── Verb: index ────────────────────────────────────────────────────────────────
// Extract PDF → JSON. For JSON output, content is a serialised JSON string.
// Parse it and extract the body array for RAG pipelines.

function verbIndex(file: string) {
  const result = extractJson(file)
  let nodes = result.elements ?? []

  // JSON output: content is a serialised JSON string — parse it to get body
  if (Array.isArray(nodes) && nodes.length === 0 && result.content) {
    try {
      const parsed = JSON.parse(result.content)
      nodes = parsed.body ?? parsed.elements ?? nodes
    } catch {
      // not JSON — fall through to text node fallback
    }
  }

  if (Array.isArray(nodes) && nodes.length > 0) {
    console.log(JSON.stringify(nodes, null, 2))
  } else {
    // No structured elements — return content as a text node
    console.log(JSON.stringify([{ type: "text", content: result.content ?? "" }], null, 2))
  }
}

// ── Verb: inspect ──────────────────────────────────────────────────────────────

function verbInspect(file: string) {
  const result = extractJson(file)
  const { metadata: meta, elements: nodes, content, qualityScore } = result
  const elementCounts: Record<string, number> = {}
  for (const item of Array.isArray(nodes) ? nodes : []) {
    if (item && typeof item === "object" && "type" in item) {
      const t = String((item as { type: string }).type)
      elementCounts[t] = (elementCounts[t] ?? 0) + 1
    }
  }

  const hasStructuredNodes = Object.keys(elementCounts).length > 0
  const nodeNote = hasStructuredNodes
    ? `${nodes.length} node(s) across ${Object.keys(elementCounts).length} type(s)`
    : nodes.length === 0
      ? "0 nodes — install additional features (layout-detection, etc.) for structured extraction"
      : `${nodes.length} node(s)`

  console.log(`\
File: ${file}
───────────────────────────────────────────────────
Format:     ${meta?.formatType ?? "unknown"}
PDF ver:    ${meta?.pdfVersion ?? "n/a"}
Encrypted:  ${meta?.isEncrypted ? "yes" : "no"}
Pages:      ${meta?.pageCount ?? "?"}
Size:       ${meta?.width ?? "?"}x${meta?.height ?? "?"}px
Created:    ${meta?.createdAt ?? "unknown"}
───────────────────────────────────────────────────
Content:    ${(content ?? "").length.toLocaleString()} chars
Nodes:      ${nodeNote}\
${
  hasStructuredNodes
    ? "\n" +
      Object.entries(elementCounts)
        .sort((a, b) => b[1] - a[1])
        .map(([t, n]) => `  ${String(n).padStart(4)} × ${t}`)
        .join("\n")
    : ""
}\
${
  qualityScore !== undefined
    ? `\n───────────────────────────────────────────────────
Quality:    ${qualityScore.toFixed(2)} / 1.00`
    : ""
}\
`)
}

// ── Help ───────────────────────────────────────────────────────────────────────

function showHelp() {
  console.log(`\
kpdf — Kreuzberg PDF wrapper

Usage:
  bun kpdf.ts <verb> --file <path>

Verbs:
  parse   Extract PDF → markdown (default)
  index   Extract PDF → JSON (structured nodes or content string)
  inspect Show metadata + structure summary
  help    Show this help

Options:
  -f, --file <path>   PDF file to extract (required)
  -v, --verb <name>   Verb to run (default: parse)
  -h, --help          Show this help

Examples:
  bun kpdf.ts parse --file report.pdf                         # markdown → stdout
  bun kpdf.ts parse --file report.pdf > out.md               # → file
  bun kpdf.ts index --file report.pdf | jq 'length'          # JSON nodes → stdout
  bun kpdf.ts index --file report.pdf > index.json           # → file for RAG
  bun kpdf.ts inspect --file report.pdf                       # metadata + structure
`)
}

// ── Main ───────────────────────────────────────────────────────────────────────

const { values, positionals } = parseArgsWithVerb()
const verb = (values.verb ?? positionals[0] ?? "parse").toLowerCase() as string

if (verb === "help") {
  showHelp()
  process.exit(0)
}

requireFile(values.file)
requireVerb(verb as Verb)

switch (verb) {
  case "parse":
    verbParse(values.file)
    break
  case "index":
    verbIndex(values.file)
    break
  case "inspect":
    verbInspect(values.file)
    break
  default:
    showHelp()
    process.exit(1)
}
