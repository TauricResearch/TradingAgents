#!/usr/bin/env bun
/**
 * Render all .dot and .mmd source files to .svg in docs/diagrams/.
 *
 * Priority:
 *   1. .dot files  → graphviz dot (always reliable)
 *   2. .mmd files  → mmdc with front-matter strip as fallback
 *
 * Usage:
 *   bun run scripts/render_diagrams.ts
 */

import { readFileSync, writeFileSync, readdirSync, existsSync } from "fs";
import { execFile } from "child_process";
import { join } from "path";
import { rmSync } from "fs";

// ─── Config ────────────────────────────────────────────────────────────────

const DIAGRAMS_DIR = join(process.cwd(), "docs", "diagrams");

// ─── Helpers ───────────────────────────────────────────────────────────────

/** Run a command, return true on exit code 0. */
async function run(
  cmd: string[],
  opts?: { capture?: boolean; cwd?: string },
): Promise<boolean> {
  return new Promise((resolve) => {
    const child = execFile(cmd[0], cmd.slice(1), {
      cwd: opts?.cwd ?? process.cwd(),
    }, (err, _stdout, stderr) => {
      if (err && opts?.capture) process.stderr.write(stderr);
      resolve(err === null);
    });
    if (!opts?.capture) child.stdout?.on("data", () => {});
    if (!opts?.capture) child.stderr?.on("data", () => {});
  });
}

function addWhiteBg(svgPath: string): void {
  const c = readFileSync(svgPath, "utf8");
  if (c.includes('fill="white"')) return;
  const patched = c.replace(
    /(<svg[^>]+>\n)/,
    '$1<rect width="100%" height="100%" fill="white"/>\n',
  );
  writeFileSync(svgPath, patched);
}

// ─── Renderers ─────────────────────────────────────────────────────────────

async function renderDot(src: string, out: string): Promise<boolean> {
  const ok = await run(["dot", "-Tsvg", src, "-o", out]);
  if (ok) addWhiteBg(out);
  return ok;
}

async function renderMmd(src: string, out: string): Promise<boolean> {
  // Fast path: mmdc handles files with no front matter
  let ok = await run(["mmdc", "-i", src, "-o", out, "-t", "neutral", "-b", "white"]);
  if (ok) return true;

  // Fallback: strip YAML front matter, then render
  const extracted = extractMermaidBlock(src);
  if (extracted === null) return false;

  const tmp = "/tmp/mmd-render.mmd";
  writeFileSync(tmp, extracted);
  ok = await run(["mmdc", "-i", tmp, "-o", out, "-t", "neutral", "-b", "white"]);
  try { rmSync(tmp); } catch {}
  return ok;
}

function extractMermaidBlock(filePath: string): string | null {
  const content = readFileSync(filePath, "utf8");
  const match = content.match(/\x60\x60\x60mermaid\n([\s\S]*?)\n\x60\x60\x60/);
  return match ? match[1] : null;
}

// ─── Main ───────────────────────────────────────────────────────────────────

async function main() {
  console.log("Rendering diagrams...\n");

  const files = readdirSync(DIAGRAMS_DIR).filter((f) =>
    f.endsWith(".dot") || f.endsWith(".mmd")
  );

  if (files.length === 0) {
    console.log("No .dot or .mmd files found in docs/diagrams/.");
    return;
  }

  let count = 0;
  for (const file of files.sort()) {
    const ext = file.endsWith(".dot") ? ".dot" : ".mmd";
    const src = join(DIAGRAMS_DIR, file);
    const out = src.replace(ext, ".svg");
    const extLabel = ext === ".dot" ? "DOT" : "MMD";

    process.stdout.write(`  ${file} (${extLabel}) → ${file.replace(ext, ".svg")} ... `);

    const ok = ext === ".dot"
      ? await renderDot(src, out)
      : await renderMmd(src, out);

    if (ok) {
      const size = existsSync(out) ? readFileSync(out).byteLength : 0;
      console.log(`✓ ${size.toLocaleString()}B`);
      count++;
    } else {
      console.log("✗ FAILED");
    }
  }

  console.log(`\nDone. Generated ${count} SVG file(s).`);
}

main();