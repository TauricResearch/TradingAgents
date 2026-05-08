#!/usr/bin/env bun
/**
 * Gate: server/views/*.tsx must not contain inline scripts.
 *
 * Allowed in views:
 *   <script src="/static/scripts/xxx.js" />
 *   <script src="https://cdn..." />
 *
 * Banned in views:
 *   dangerouslySetInnerHTML with __html
 *   <script>{...}</script> (literal JSX script block with body)
 *   function xxxScript() { return `...` }
 *   Any <script> without a src attribute
 */

import { readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"

const VIEWS_DIR = join(import.meta.dir, "..", "src", "server", "views")
const files = readdirSync(VIEWS_DIR).filter((f) => f.endsWith(".tsx"))

const bannedPatterns = [
  { regex: /dangerouslySetInnerHTML\s*=/g, name: "dangerouslySetInnerHTML" },
  { regex: /<script\s*>\s*\{`/g, name: "literal <script>{`...`}</script> block" },
  { regex: /function\s+\w+Script\s*\(\)\s*:/g, name: "function xxxScript() wrapper" },
  { regex: /<script\b(?!.*\bsrc\b)/g, name: "<script> without src attribute" },
]

let errors = 0

for (const file of files) {
  const content = readFileSync(join(VIEWS_DIR, file), "utf-8")
  for (const pattern of bannedPatterns) {
    const matches = content.match(pattern.regex)
    if (matches) {
      console.error(`\u274c BANNED: ${file} contains ${pattern.name}`)
      errors += matches.length
    }
  }
}

// Also verify serveStatic root is tight
const INDEX = join(import.meta.dir, "..", "src", "server", "index.tsx")
const indexContent = readFileSync(INDEX, "utf-8")
const hasLiteralRoot = indexContent.includes('root: "./server/static"')
const hasComputedRoot = indexContent.includes('resolve(import.meta.dir, "static")')
if (!hasLiteralRoot && !hasComputedRoot) {
  console.error(
    "\u274c BANNED: src/server/index.tsx does not lock serveStatic to a local static directory",
  )
  errors++
}

if (errors > 0) {
  console.error(`\n${errors} violation(s) found.`)
  console.error("Fix: extract JS to server/static/scripts/*.js and reference with <script src>")
  console.error("See: playbooks/htmx-playbook.md -> 'Client-Side JS: External Files, Not Inline'")
  process.exit(1)
}

console.log(`\u2705 All ${files.length} view files clean. No inline scripts found.`)
console.log("\u2705 serveStatic root locked to ./server/static.")
process.exit(0)
