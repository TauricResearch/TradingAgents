// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The Bun runtime a cross-compiled executable is built on, as package-lock.json locks it: the target's
 * package is downloaded from the address the lockfile records and refused unless its sha512 matches the
 * lockfile's integrity. Run with Bun: `bun scripts/runtime.ts <target> <dir>`, the target being one of
 * Bun's (bun-linux-x64, ...); it prints the path of the runtime it unpacked into <dir>.
 */
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { REQUEST_MS } from "../src/contracts/limits.js";

/** Bun's compile targets, by the runtime package npm installs for each. */
const PACKAGES: Record<string, string> = {
  "bun-linux-x64": "@oven/bun-linux-x64",
  "bun-linux-arm64": "@oven/bun-linux-aarch64",
  "bun-darwin-x64": "@oven/bun-darwin-x64",
  "bun-darwin-arm64": "@oven/bun-darwin-aarch64",
};

type Lockfile = { packages: Record<string, { resolved?: string; integrity?: string } | undefined> };

/** Where the lockfile says the target's runtime package comes from, and what it must hash to. */
export function lockedRuntime(lock: Lockfile, target: string): { resolved: string; integrity: string } {
  const name = PACKAGES[target];
  if (!name) throw new Error(`no runtime package is known for the target ${target}`);
  const entry = lock.packages[`node_modules/${name}`];
  if (!entry?.resolved || !entry.integrity?.startsWith("sha512-")) {
    throw new Error(`package-lock.json locks no sha512 for ${name}`);
  }
  return { resolved: entry.resolved, integrity: entry.integrity };
}

/** The integrity string of `bytes`, as npm writes it. */
export function integrityOf(bytes: Uint8Array): string {
  return `sha512-${createHash("sha512").update(bytes).digest("base64")}`;
}

// Run directly by Bun, not when a test imports the functions above.
if ((import.meta as { main?: boolean }).main) {
  const [target, dir] = process.argv.slice(2) as [string, string];
  const lock = JSON.parse(readFileSync("package-lock.json", "utf8")) as Lockfile;
  const { resolved, integrity } = lockedRuntime(lock, target);
  const response = await fetch(resolved, { signal: AbortSignal.timeout(REQUEST_MS.runtimeDownload) });
  if (!response.ok) throw new Error(`${resolved} answered ${response.status}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (integrityOf(bytes) !== integrity) throw new Error(`${resolved} does not match package-lock.json`);
  const into = join(dir, target);
  mkdirSync(into, { recursive: true });
  const archive = join(into, "runtime.tgz");
  writeFileSync(archive, bytes);
  const unpacked = spawnSync("tar", ["-xzf", archive, "-C", into, "package/bin/bun"], { stdio: "inherit" });
  if (unpacked.status !== 0) throw new Error(`could not unpack ${archive}`);
  console.log(join(into, "package", "bin", "bun"));
}
