// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * `tradingagents update`: replace this executable with the latest release, as the installer would. The
 * release is the one GitHub marks latest, as for the update check and the installer; the download is checked
 * against the release's SHA256SUMS (exactly one line for the file), written beside the executable, started
 * once (`--version` must say the new version), then renamed over it, so the old file is replaced whole or
 * not at all. A lock keeps two updates from racing. A copy it cannot or should not replace (one that is
 * not an installed release, one a package manager owns, one in a folder the user cannot write) is left
 * alone, with what to do instead.
 */
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { accessSync, constants, promises as fs, realpathSync } from "node:fs";
import { basename, dirname, join, sep } from "node:path";
import semver from "semver";
import { INSTALL_COMMAND, NPM_PLATFORM_PREFIX, NPM_UPDATE_COMMAND } from "../config/index.js";
import { APP_NAME, errorText, message } from "../contracts/index.js";
import { REQUEST_MS, UPDATES } from "../contracts/limits.js";
import { Lock } from "../store/lock.js";
import { capped, latestRelease } from "./updates.js";

export type UpdateResult =
  | { kind: "updated"; from: string; to: string }
  | { kind: "current"; version: string }
  /** Nothing was changed, for the reason given (a sentence for the person). */
  | { kind: "refused"; reason: string };

/** How a copy is updated from here: by `selfUpdate`, or by the package manager's command. */
export type UpdateWay = { kind: "self" } | { kind: "npm"; command: string };

export type UpdateDeps = {
  /** The running executable (process.execPath). */
  execPath: string;
  current: string;
  /** Where the latest release is read and this platform's file in it; undefined when there is none. */
  lookup: { url: string; asset: string } | undefined;
  /** The lock file's path (in the home directory). */
  lockPath: string;
  fetch?: typeof globalThis.fetch;
  /** Starts a file with arguments and gives what it printed. */
  run?: (file: string, args: string[]) => Promise<string>;
  signal?: AbortSignal;
};

/** Where npm installs the package that carries the executable for each platform (see scripts/npm-packages.ts). */
const NPM_PLATFORM_DIR = `${sep}node_modules${sep}${NPM_PLATFORM_PREFIX.split("/").join(sep)}`;

/** Path parts that mean a package manager owns the file. */
const MANAGED = [
  `${sep}node_modules${sep}`,
  `${sep}Cellar${sep}`,
  `${sep}homebrew${sep}`,
  `${sep}linuxbrew${sep}`,
  `${sep}nix${sep}store${sep}`,
];

/**
 * How the copy at `execPath` can be updated from here: replaced by `selfUpdate` (an installed release in a
 * folder the user can write), or by npm (an npm install); none for anything else (a development run, a copy
 * another package manager owns, a folder the user cannot write), which is updated another way.
 */
export function updateWay(execPath: string): UpdateWay | undefined {
  let target: string;
  try {
    target = realpathSync(execPath);
  } catch {
    return undefined;
  }
  if (target.includes(NPM_PLATFORM_DIR)) return { kind: "npm", command: NPM_UPDATE_COMMAND };
  if (!basename(target).startsWith(APP_NAME) || MANAGED.some((part) => target.includes(part)))
    return undefined;
  try {
    accessSync(dirname(target), constants.W_OK);
  } catch {
    return undefined;
  }
  return { kind: "self" };
}

/**
 * How an update went, as the person is told: `failed` when it was refused or could not finish, `updated` when
 * a newer version is in place.
 */
export async function updateReport(
  update: () => Promise<UpdateResult>,
): Promise<{ text: string; failed: boolean; updated: boolean }> {
  try {
    const result = await update();
    if (result.kind === "refused") return { text: result.reason, failed: true, updated: false };
    if (result.kind === "current")
      return { text: message("update.current", { version: result.version }), failed: false, updated: false };
    return {
      text: message("update.updated", { from: result.from, to: result.to }),
      failed: false,
      updated: true,
    };
  } catch (error) {
    return { text: message("update.failed", { reason: errorText(error) }), failed: true, updated: false };
  }
}

export async function selfUpdate(deps: UpdateDeps): Promise<UpdateResult> {
  const refused = (reason: string): UpdateResult => ({ kind: "refused", reason });
  // The file itself, not a link to it: the link stays and points at the new file.
  const target = await fs.realpath(deps.execPath);
  if (!basename(target).startsWith(APP_NAME))
    return refused(message("update.notRelease", { install: INSTALL_COMMAND }));
  if (target.includes(NPM_PLATFORM_DIR))
    return refused(message("update.npm", { command: NPM_UPDATE_COMMAND }));
  if (MANAGED.some((part) => target.includes(part))) return refused(message("update.managed"));
  const dir = dirname(target);
  try {
    await fs.access(dir, constants.W_OK);
  } catch {
    return refused(message("update.unwritable", { dir, install: INSTALL_COMMAND }));
  }
  if (!deps.lookup) return refused(message("update.none"));

  const lock = await Lock.acquire(deps.lockPath);
  if (!(lock instanceof Lock)) {
    const path = lock.stuck ?? deps.lockPath;
    return refused(
      message("update.busy", {
        path,
        ...(lock.heldBy ? { pid: lock.heldBy.pid, host: lock.heldBy.host } : {}),
      }),
    );
  }
  const partial = join(dir, `.${APP_NAME}.${process.pid}`);
  try {
    const fetchImpl = deps.fetch ?? fetch;
    const signal = AbortSignal.any([
      ...(deps.signal ? [deps.signal] : []),
      AbortSignal.timeout(REQUEST_MS.updateDownload),
    ]);
    const newest = await latestRelease(deps.lookup.url, deps.lookup.asset, fetchImpl, signal);
    if (!newest) return refused(message("update.none"));
    if (semver.valid(deps.current) && !semver.gt(newest.version, deps.current)) {
      return { kind: "current", version: deps.current };
    }
    const sums = (await download(fetchImpl, newest.sums, UPDATES.sumsBytes, signal)).toString("utf8");
    const expected = checksumOf(sums, deps.lookup.asset);
    if (!expected) return refused(message("update.noChecksum", { name: deps.lookup.asset }));
    const digest = await downloadTo(fetchImpl, newest.executable, partial, signal);
    if (digest !== expected) return refused(message("update.badChecksum"));
    const run = deps.run ?? startOnce;
    const said = await run(partial, ["--version"]).catch(() => "");
    if (said.trim() !== newest.version) return refused(message("update.wontStart"));
    await fs.rename(partial, target);
    return { kind: "updated", from: deps.current, to: newest.version };
  } finally {
    await fs.rm(partial, { force: true });
    await lock.release();
  }
}

/** The checksum SHA256SUMS gives `name`: exactly one well-formed line for it, else none. */
export function checksumOf(sums: string, name: string): string | undefined {
  const found = sums
    .split("\n")
    .map((line) => /^([0-9a-f]{64}) {2}(.+)$/.exec(line))
    .filter((match) => match?.[2] === name);
  return found.length === 1 ? found[0]?.[1] : undefined;
}

/** An https answer's body, refused past `limit` bytes or when a redirect left https. */
async function* body(
  fetchImpl: typeof globalThis.fetch,
  url: string,
  limit: number,
  signal: AbortSignal,
): AsyncGenerator<Uint8Array> {
  if (!url.startsWith("https://")) throw new Error(`a release file is not on https: ${url}`);
  const response = await fetchImpl(url, { method: "GET", credentials: "omit", redirect: "follow", signal });
  if (!response.ok) throw new Error(`${url} answered ${response.status}`);
  if (response.url && !response.url.startsWith("https://"))
    throw new Error(`${url} was redirected off https`);
  yield* capped(response, limit, `${url} is larger than expected`);
}

async function download(
  fetchImpl: typeof globalThis.fetch,
  url: string,
  limit: number,
  signal: AbortSignal,
): Promise<Buffer> {
  const chunks: Uint8Array[] = [];
  for await (const chunk of body(fetchImpl, url, limit, signal)) chunks.push(chunk);
  return Buffer.concat(chunks);
}

/** Write the download to a new file at `path` (executable) and give its SHA-256. */
async function downloadTo(
  fetchImpl: typeof globalThis.fetch,
  url: string,
  path: string,
  signal: AbortSignal,
): Promise<string> {
  const hash = createHash("sha256");
  const file = await fs.open(path, "wx", 0o755);
  try {
    for await (const chunk of body(fetchImpl, url, UPDATES.executableBytes, signal)) {
      hash.update(chunk);
      await file.write(chunk);
    }
  } finally {
    await file.close();
  }
  // Whatever the umask, the new file runs.
  await fs.chmod(path, 0o755);
  return hash.digest("hex");
}

/** Start `file` once and give what it printed, within REQUEST_MS.updateStart. */
function startOnce(file: string, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(file, args, { timeout: REQUEST_MS.updateStart }, (error, stdout) =>
      error ? reject(error) : resolve(String(stdout)),
    );
  });
}
