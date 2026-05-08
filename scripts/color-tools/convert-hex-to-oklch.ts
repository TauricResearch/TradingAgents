#!/usr/bin/env bun
/**
 * convert-hex-to-oklch.ts
 *
 * Converts hex color values inside a CSS `:root` block to oklch(),
 * preserving the original hex in a trailing comment.
 *
 * Usage:
 *   bun scripts/color-tools/convert-hex-to-oklch.ts [input.css] [output.css]
 *
 * Defaults:
 *   input  → server/static/style.css
 *   output → same as input (in-place)
 */
import { readFileSync, writeFileSync } from "node:fs"
import { convertCSS } from "colorizr"

const HEX_RE = /#([0-9a-fA-F]{3,8})\b/g

function hexToOklch(hex: string): string | null {
  try {
    return convertCSS(hex, "oklch")
  } catch {
    return null
  }
}

function convertLine(line: string): string {
  const matches = [...line.matchAll(HEX_RE)]
  if (matches.length === 0) return line

  let result = line
  let comment = ""

  // Build replacement from right-to-left so indices stay valid
  for (let i = matches.length - 1; i >= 0; i--) {
    const m = matches[i]
    const hex = m[0]
    const oklch = hexToOklch(hex)
    if (!oklch) continue

    const idx = m.index ?? 0
    const before = result.slice(0, idx)
    const after = result.slice(idx + hex.length)
    result = before + oklch + after

    // Collect original hex values for comment
    if (!comment.includes(hex)) {
      comment = comment ? `${comment}, ${hex}` : hex
    }
  }

  // Append trailing comment with original hexes
  if (comment) {
    const existingComment = result.match(/(\/\*.*\*\/)$/)?.[0]
    if (existingComment) {
      // Merge into existing comment
      result = result.replace(
        existingComment,
        `/* ${comment}, ${existingComment.replace(/\/\*\s*/, "").replace(/\s*\*\/$/, "")} */`,
      )
    } else {
      result += ` /* ${comment} */`
    }
  }

  return result
}

function main() {
  const inputPath = process.argv[2] || "src/server/static/style.css"
  const outputPath = process.argv[3] || inputPath

  const css = readFileSync(inputPath, "utf-8")

  // Find :root block
  const rootMatch = css.match(/:root\s*\{([\s\S]*?)\}/)
  if (!rootMatch) {
    console.error(`No :root block found in ${inputPath}`)
    process.exit(1)
  }

  const originalBlock = rootMatch[0]
  const inner = rootMatch[1]

  const lines = inner.split("\n")
  const convertedLines = lines.map((line) => {
    if (!line.trim() || line.trim().startsWith("/*")) return line
    return convertLine(line)
  })

  const newBlock = `:root {${convertedLines.join("\n")}\n}`
  const newCss = css.replace(originalBlock, newBlock)

  writeFileSync(outputPath, newCss, "utf-8")

  const changed = lines
    .map((orig, i) => ({ orig: orig.trim(), conv: convertedLines[i].trim() }))
    .filter((x) => x.orig !== x.conv && x.orig.length > 0)

  console.log(`Wrote ${outputPath}`)
  console.log(`Converted ${changed.length} color declarations:`)
  for (const c of changed) {
    console.log(`  ${c.orig} → ${c.conv}`)
  }
}

main()
