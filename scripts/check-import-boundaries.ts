/**
 * Import boundary gate — verifies the silo enforces its layer contracts.
 *
 * Rules (from src/README.md):
 *   - src/cli/    must NOT import from src/server/
 *   - src/server/ must NOT import from src/cli/
 *   - scripts/    must NOT import from src/cli/ or src/server/
 *
 * All other imports are allowed (src/lib/, src/server/lib/, relative, etc.).
 */

import { readdirSync, readFileSync } from "node:fs"
import { join, relative } from "node:path"

const ROOT = join(import.meta.dir, "..", "src")

type FileVisitor = (relPath: string, content: string) => void

function walkDir(dir: string, ext: string[], visitor: FileVisitor): void {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      // Skip node_modules, .git, dist, etc.
      if (["node_modules", ".git", "dist", ".next", "static"].includes(entry.name)) continue
      walkDir(full, ext, visitor)
    } else if (ext.some((e) => entry.name.endsWith(e))) {
      const rel = relative(ROOT, full)
      try {
        visitor(rel, readFileSync(full, "utf-8"))
      } catch {
        // Skip files that can't be read
      }
    }
  }
}

// Regex to extract all import-from paths from a file
function checkFile(
  relPath: string,
  content: string,
): Array<{ line: number; from: string; reason: string }> {
  const violations: Array<{ line: number; from: string; reason: string }> = []
  const lines = content.split("\n")

  // Determine which silo tier this file belongs to
  const isCli = relPath.startsWith("cli\\") || relPath.startsWith("cli/")
  const isScripts = relPath.startsWith("scripts\\") || relPath.startsWith("scripts/")
  const isServer = relPath.startsWith("server\\") || relPath.startsWith("server/")

  // Import source patterns to check
  const SERVER_PATTERNS = [
    { pattern: /src[/\\]server/, label: "src/server" },
    { pattern: /src[/\\]server[/\\]lib/, label: "src/server/lib" },
    { pattern: /src[/\\]server[/\\]routes/, label: "src/server/routes" },
    { pattern: /src[/\\]server[/\\]views/, label: "src/server/views" },
  ]

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const match = line.match(
      /import\s+(?:type\s+)?(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)?\s*from\s+['"]([^'"]+)['"]/,
    )
    if (!match) continue

    const importFrom = match[1]

    // Skip: relative imports within same tier, node_modules, external packages
    if (
      importFrom.startsWith(".") ||
      importFrom.startsWith("node:") ||
      importFrom.startsWith("@") ||
      !importFrom.startsWith("src")
    ) {
      continue
    }

    // Rule: CLI must not import from server
    if (isCli) {
      for (const { pattern, label } of SERVER_PATTERNS) {
        if (pattern.test(importFrom)) {
          violations.push({
            line: i + 1,
            from: importFrom,
            reason: `src/cli/ may not import from ${label}`,
          })
        }
      }
    }

    // Rule: Server must not import from CLI
    if (isServer && importFrom.startsWith("src/cli")) {
      violations.push({
        line: i + 1,
        from: importFrom,
        reason: "src/server/ may not import from src/cli/",
      })
    }

    // Rule: scripts must not import from cli or server
    if (isScripts && (importFrom.startsWith("src/cli") || importFrom.startsWith("src/server"))) {
      violations.push({
        line: i + 1,
        from: importFrom,
        reason: "scripts/ may not import from src/cli/ or src/server/",
      })
    }
  }

  return violations
}

// ── Main ───────────────────────────────────────────────────────────────────────

const srcDir = join(import.meta.dir, "..", "src")
const allViolations: Array<{ file: string; line: number; from: string; reason: string }> = []

walkDir(srcDir, [".ts", ".tsx"], (relPath, content) => {
  const violations = checkFile(relPath, content)
  for (const v of violations) {
    allViolations.push({ file: relPath, ...v })
  }
})

if (allViolations.length > 0) {
  console.error("✗ Import boundary violations found:")
  console.error("")
  for (const v of allViolations) {
    console.error(`  ${v.file}:${v.line}  imports "${v.from}" — ${v.reason}`)
  }
  console.error("")
  console.error(`Total: ${allViolations.length} violation(s)`)
  console.error("")
  console.error("Fix: move shared code to src/lib/ or src/server/lib/")
  process.exit(1)
}

console.log("✓ Import boundaries: no violations")
process.exit(0)
