// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The update's lock: a refusal names the file to remove, a lock held by a live process is not taken,
 * and one whose holder is gone is.
 */
import { expect, test } from "bun:test";
import { spawn } from "node:child_process";
import { promises as fs } from "node:fs";
import { hostname, tmpdir } from "node:os";
import { join } from "node:path";
import { selfUpdate } from "../src/cli/self-update.js";

/** The version running, and the one the lookup answers: not newer, so an update that runs ends at "current". */
const CURRENT = "2.0.0";
const RELEASE = "1.0.0";
const ASSET = "tradingagents-test";

/** The lookup's answer: the one release, with this platform's file and the checksums in it. */
function answer(): Response {
  return new Response(
    JSON.stringify({
      tag_name: RELEASE,
      assets: [
        { name: ASSET, browser_download_url: `https://releases.example/${ASSET}` },
        { name: "SHA256SUMS", browser_download_url: "https://releases.example/SHA256SUMS" },
      ],
    }),
  );
}

/** An install the update can replace: a writable executable named as a release, and the lock beside it. */
async function install(): Promise<{ execPath: string; lockPath: string }> {
  const dir = await fs.mkdtemp(join(tmpdir(), "self-update-"));
  const execPath = join(dir, "tradingagents");
  await fs.writeFile(execPath, "#!/bin/sh\n", { mode: 0o755 });
  await fs.chmod(execPath, 0o755);
  return { execPath, lockPath: join(dir, "update.lock") };
}

/** An update of the copy at `execPath`, locked at `lockPath`, the lookup answered without network. */
function update(execPath: string, lockPath: string) {
  return selfUpdate({
    execPath,
    current: CURRENT,
    lookup: { url: "https://releases.example/latest", asset: ASSET },
    lockPath,
    fetch: () => Promise.resolve(answer()),
  });
}

/** The refusal's text (empty for a run that was not refused, which the kind assertion names). */
async function refusalOf(execPath: string, lockPath: string): Promise<string> {
  const result = await update(execPath, lockPath);
  expect(result.kind).toBe("refused");
  return result.kind === "refused" ? result.reason : "";
}

/** Whether a file is there. */
async function exists(path: string): Promise<boolean> {
  try {
    await fs.stat(path);
    return true;
  } catch {
    return false;
  }
}

test("a lock an update left as a bare process number is refused naming the file to remove", async () => {
  const { execPath, lockPath } = await install();
  // What an update of this version wrote: a bare process number, which a live process reusing it kept held.
  await fs.writeFile(lockPath, String(process.ppid));
  expect(await refusalOf(execPath, lockPath)).toContain(lockPath);
  expect(await exists(lockPath)).toBe(true);
});

test("a lock held by a live process is not taken, and the refusal names the file", async () => {
  const { execPath, lockPath } = await install();
  // A live holder on this host, with no start time to compare: the same verdict everywhere.
  await fs.writeFile(lockPath, JSON.stringify({ pid: process.ppid, host: hostname(), token: "held" }));
  expect(await refusalOf(execPath, lockPath)).toContain(lockPath);
  expect(await exists(lockPath)).toBe(true);
});

test("a lock whose holder is gone is taken over", async () => {
  const { execPath, lockPath } = await install();
  const child = spawn("/bin/sleep", ["0"]);
  const pid = child.pid;
  await new Promise((resolve) => child.on("exit", resolve));
  // Wait until the number names no process.
  for (;;) {
    try {
      process.kill(pid, 0);
      await new Promise((resolve) => setTimeout(resolve, 10));
    } catch {
      break;
    }
  }
  await fs.writeFile(lockPath, JSON.stringify({ pid, host: hostname(), token: "gone" }));
  const result = await update(execPath, lockPath);
  expect(result).toEqual({ kind: "current", version: CURRENT });
  expect(await exists(lockPath)).toBe(false);
});
