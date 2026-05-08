#!/usr/bin/env bun
/**
 * Push with diagram regeneration.
 *
 * Regenerates diagrams, commits changes if any, then pushes.
 * Replaces inline bash in justfile.
 */

import { execSync } from "node:child_process"

function hasChanges(): boolean {
  try {
    execSync("git diff --quiet docs/diagrams/gn-* docs/diagrams/*.svg", { stdio: "pipe" })
    return false
  } catch {
    return true
  }
}

function main() {
  console.log("=== Regenerating diagrams ===")
  execSync("just regen-diagrams", { stdio: "inherit" })

  if (hasChanges()) {
    console.log("\n=== Diagrams changed. Committing... ===")
    execSync(
      "git add docs/diagrams/gn-*.dot docs/diagrams/gn-*.svg docs/diagrams/gn-*.png 2>/dev/null || true",
    )
    execSync("git add docs/diagrams/*.svg 2>/dev/null || true")
    execSync('git commit -m "chore(diagrams): auto-regenerate before push" --no-verify || true', {
      stdio: "inherit",
    })
  } else {
    console.log("\nNo diagram changes.")
  }

  console.log("\n=== Pushing ===")
  execSync("git push", { stdio: "inherit" })
}

main()
