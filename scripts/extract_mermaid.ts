#!/usr/bin/env bun
/**
 * Extract the mermaid block from a .mmd file (strips YAML front matter).
 *
 * Usage:
 *   bun run scripts/extract_mermaid.ts <input.mmd> <output.mmd>
 *   bun scripts/extract_mermaid.ts input.mmd output.mmd
 *
 * Example:
 *   bun scripts/extract_mermaid.ts docs/diagrams/src/system-overview.mmd /tmp/out.mmd
 */

import { readFileSync, writeFileSync } from "fs";

const [, , inputPath, outputPath] = process.argv;

if (!inputPath || !outputPath) {
  console.error(`Usage: ${process.argv[1]} <input.mmd> <output.mmd>`);
  process.exit(1);
}

const content = readFileSync(inputPath, "utf8");

const match = content.match(/\x60\x60\x60mermaid\n([\s\S]*?)\n\x60\x60\x60/);
if (!match) {
  console.error(`No mermaid block found in ${inputPath}`);
  process.exit(1);
}

writeFileSync(outputPath, match[1]);