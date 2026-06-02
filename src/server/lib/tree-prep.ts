/**
 * Prepared input builder for @pierre/trees file explorer.
 * Shapes tree data on the server so the client only hydrates.
 */

import { readdirSync } from "node:fs"
import type { FileTreePreparedInput } from "@pierre/trees"
import { prepareFileTreeInput } from "@pierre/trees"

export type { FileTreePreparedInput }

/** Build prepared input from a flat list of repo file paths. */
export function buildRepoTree(paths: readonly string[]): FileTreePreparedInput {
  return prepareFileTreeInput(paths, {
    flattenEmptyDirectories: true,
  })
}

/**
 * Fetch repository file paths (git-tracked only) for the explorer.
 * Uses `git ls-files` from the project root.
 */
export function getRepoPaths(): string[] {
  const proc = Bun.spawnSync(
    ["git", "ls-files", "--full-name", "--", "src", "scripts", "playbooks", "docs", "briefs"],
    {
      stdout: "pipe",
      stderr: "pipe",
    },
  )
  if (!proc.success) {
    return fsFallbackPaths()
  }
  return proc.stdout
    .toString()
    .trim()
    .split("\n")
    .filter((p) => p.length > 0)
}

/** Fallback: scan filesystem directly when git is unavailable. */
function fsFallbackPaths(): string[] {
  const paths: string[] = []
  const dirs = ["src", "scripts", "playbooks", "docs", "briefs"]
  for (const dir of dirs) {
    try {
      walk(dir, (p) => paths.push(p))
    } catch {
      // skip missing dirs
    }
  }
  return paths.sort()
}

function walk(dir: string, onFile: (p: string) => void): void {
  const entries = readdirSync(dir, { withFileTypes: true })
  for (const entry of entries) {
    const full = `${dir}/${entry.name}`
    if (entry.isDirectory()) {
      if (entry.name.startsWith(".") || entry.name === "node_modules") continue
      walk(full, onFile)
    } else {
      onFile(full)
    }
  }
}

/**
 * File type classification for the explorer.
 * Four categories: image, markdown, text, other.
 */
export type FileKind = "image" | "markdown" | "text" | "other"

/** Maps extension → FileKind. */
const EXT_MAP: Record<string, FileKind> = {
  // Images — rendered inline
  png: "image",
  svg: "image",
  gif: "image",
  webp: "image",
  // Markdown — rendered as HTML
  md: "markdown",
  mdx: "markdown",
  // Text — syntax-highlighted or raw
  ts: "text",
  tsx: "text",
  js: "text",
  jsx: "text",
  py: "text",
  json: "text",
  yaml: "text",
  yml: "text",
  toml: "text",
  sql: "text",
  css: "text",
  sh: "text",
  bash: "text",
  // Everything else
}

export function classifyFile(path: string): FileKind {
  const ext = path.split(".").pop()?.toLowerCase() ?? ""
  return EXT_MAP[ext] ?? "other"
}

/** Highlight.js language tag for a file path. */
export function fileLanguageTag(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() ?? ""
  switch (ext) {
    case "ts":
    case "tsx":
      return "typescript"
    case "js":
    case "jsx":
      return "javascript"
    case "py":
      return "python"
    case "json":
      return "json"
    case "yaml":
    case "yml":
      return "yaml"
    case "toml":
      return "ini"
    case "sql":
      return "sql"
    case "css":
      return "css"
    case "md":
    case "mdx":
      return "markdown"
    case "sh":
    case "bash":
      return "bash"
    default:
      return "text"
  }
}

// ── Navigation Tree POC ────────────────────────────────────

/**
 * Navigation structure for the site. Mirrors the dashboard routes.
 * This is a POC of the "functional navigation menu as a tree" concept.
 * @pierre/trees treats these as file paths, so each nav entry gets a fake
 * directory prefix to group them (e.g. "nav/Pages/portfolio").
 */
export const NAV_STRUCTURE = {
  Pages: [
    { label: "Portfolio", path: "/portfolio" },
    { label: "Intelligence", path: "/intelligence" },
    { label: "Workflow", path: "/workflow" },
    { label: "Analyze", path: "/analyze" },
    { label: "Signals", path: "/signals" },
    { label: "History", path: "/history" },
    { label: "Holdings", path: "/holdings" },
    { label: "Exits", path: "/exits" },
    { label: "Prospects", path: "/prospects" },
    { label: "Governance", path: "/governance" },
    { label: "Benchmark", path: "/benchmark" },
    { label: "Feedback", path: "/feedback" },
    { label: "Alerts", path: "/alerts" },
    { label: "Screenings", path: "/screenings" },
    { label: "Explorer", path: "/explorer" },
    { label: "Test Datatype", path: "/test/datatype" },
    { label: "About", path: "/about" },
  ],
  API: [
    { label: "positions", path: "/api/positions" },
    { label: "analyze", path: "/api/analyze" },
    { label: "signals", path: "/api/signals" },
    { label: "prices", path: "/api/prices" },
    { label: "analyses", path: "/api/analyses" },
    { label: "holdings", path: "/api/holdings" },
    { label: "prospects", path: "/api/prospects" },
    { label: "workflow", path: "/api/workflow" },
    { label: "portfolio/intelligence", path: "/api/portfolio/intelligence" },
    { label: "portfolio/balance", path: "/api/portfolio/balance" },
    { label: "trade-plan", path: "/api/trade-plan" },
    { label: "alerts", path: "/api/alerts" },
    { label: "screenings", path: "/api/screenings" },
    { label: "portfolio/summary", path: "/api/portfolio/summary" },
  ],
} as const

/**
 * Convert the nav structure into flat paths for @pierre/trees.
 * Each entry becomes "nav/{Group}/{label}" so the tree can group them.
 */
export function buildNavTreePaths(): string[] {
  const paths: string[] = []
  for (const [group, entries] of Object.entries(NAV_STRUCTURE)) {
    for (const entry of entries) {
      // Use the real path as the "file" so we can look it up on selection
      paths.push(`nav/${group}/${entry.label}`)
    }
  }
  return paths
}

/**
 * Resolve a nav tree path back to the real URL.
 * "nav/Pages/Portfolio" → "/portfolio"
 */
export function resolveNavPath(treePath: string): string | null {
  const match = treePath.match(/^nav\/(Pages|API)\/(.*)$/)
  if (!match) return null
  const [, , label] = match
  for (const entries of Object.values(NAV_STRUCTURE)) {
    const entry = entries.find((e) => e.label === label)
    if (entry) return entry.path
  }
  return null
}
