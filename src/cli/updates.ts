// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The check for a newer release. The request is a bare GET of one configured URL: no identifiers,
 * cookies or usage data. At most once a day, in the background; what it finds is told at the next start.
 */
import { promises as fs, readFileSync } from "node:fs";
import { dirname } from "node:path";
import semver from "semver";
import { ENV, RELEASE_URL, writeAtomic } from "../config/index.js";
import { message } from "../contracts/index.js";
import { REQUEST_MS, UPDATES } from "../contracts/limits.js";

/**
 * Where the newest release's version is read: undefined when no release qualifies, an error when the
 * lookup failed.
 */
export type UpdateSource = { url: string; latest(signal: AbortSignal): Promise<string | undefined> };

/** The source to use: the public repository's latest release; none when opted out. */
export function updateSource(env: NodeJS.ProcessEnv = process.env): UpdateSource | undefined {
  if (env[ENV.noUpdateCheck]) return undefined;
  const lookup = releaseLookup();
  return lookup ? githubLatest(lookup.url, lookup.asset) : undefined;
}

/** Where the latest release is read and this platform's file in it; none for a platform no release is built for. */
export function releaseLookup(): { url: string; asset: string } | undefined {
  const asset = releaseAsset();
  return asset ? { url: RELEASE_URL, asset } : undefined;
}

/** The release file of the executable for a platform, as the release workflow names it. */
export function releaseAsset(
  platform: NodeJS.Platform = process.platform,
  arch: string = process.arch,
): string | undefined {
  const os = ({ linux: "linux", darwin: "darwin" } as Partial<Record<NodeJS.Platform, string>>)[platform];
  const cpu = ({ x64: "x64", arm64: "arm64" } as Record<string, string>)[arch];
  return os && cpu ? `tradingagents-${os}-${cpu}` : undefined;
}

/**
 * GitHub's latest release: the URL answers with the one release GitHub marks latest
 * (https://api.github.com/repos/<owner>/<repo>/releases/latest).
 */
export function githubLatest(
  url: string,
  asset: string,
  fetchImpl: typeof globalThis.fetch = fetch,
): UpdateSource {
  return {
    url,
    async latest(signal) {
      return (await latestRelease(url, asset, fetchImpl, signal))?.version;
    },
  };
}

/** A release to install: its version, and where this platform's executable and SHA256SUMS download from. */
type Release = { version: string; executable: string; sums: string };

/** The release GitHub marks latest, as `releaseOf` reads it. */
export async function latestRelease(
  url: string,
  asset: string,
  fetchImpl: typeof globalThis.fetch,
  signal: AbortSignal,
): Promise<Release | undefined> {
  const response = await fetchImpl(url, { method: "GET", credentials: "omit", redirect: "error", signal });
  if (!response.ok) throw new Error(`the release lookup answered ${response.status}`);
  return releaseOf(JSON.parse(await bounded(response)), asset);
}

/**
 * A release as one to install: tagged MAJOR.MINOR.PATCH (an optional leading "v"), with `asset` and
 * SHA256SUMS among its files, each with a download URL of printable ASCII without spaces; else none.
 */
export function releaseOf(release: unknown, asset: string): Release | undefined {
  const r = (typeof release === "object" && release !== null ? release : {}) as {
    tag_name?: unknown;
    assets?: unknown;
  };
  const tag = typeof r.tag_name === "string" ? r.tag_name : "";
  const version = /^v?((0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*))$/.exec(tag)?.[1];
  const files = Array.isArray(r.assets)
    ? (r.assets as { name?: unknown; browser_download_url?: unknown }[])
    : [];
  const url = (name: string) =>
    files.find(
      (a) =>
        a?.name === name &&
        typeof a.browser_download_url === "string" &&
        /^[\x21-\x7e]+$/.test(a.browser_download_url),
    )?.browser_download_url as string | undefined;
  const executable = url(asset);
  const sums = url("SHA256SUMS");
  return version && executable && sums ? { version, executable, sums } : undefined;
}

/** An answer's body as it comes, refused with `tooLarge` once it passes `limit` bytes. */
export async function* capped(
  response: Response,
  limit: number,
  tooLarge: string,
): AsyncGenerator<Uint8Array> {
  const reader = response.body?.getReader();
  if (!reader) return;
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    size += value.byteLength;
    if (size > limit) {
      await reader.cancel();
      throw new Error(tooLarge);
    }
    yield value;
  }
}

/** The answer's text, refused past UPDATES.answerBytes. */
async function bounded(response: Response): Promise<string> {
  const chunks: Uint8Array[] = [];
  for await (const chunk of capped(response, UPDATES.answerBytes, "the release lookup answered too much"))
    chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

/** What the last check found, and a release the person chose to skip until a newer one is out. */
type State = { url: string; checkedAt: number; latest?: string; skipped?: string };

/**
 * What an earlier check found: `available`, a release newer than this one that was not skipped, with its
 * notice; and a check in the background when the last one is a day old. A failed look is recorded, so it
 * waits a day too; one stopped by the session's end is not.
 */
export function checkForUpdate({
  source,
  current,
  statePath,
  now,
  signal,
  upgradeCommand,
}: {
  source: UpdateSource;
  current: string;
  statePath: string;
  now: () => number;
  signal: AbortSignal;
  upgradeCommand?: string | undefined;
}): { available?: string; notice?: string; refresh: Promise<void> } {
  const known = readState(statePath, source.url);
  const latest = known?.latest;
  const newer =
    latest !== undefined &&
    semver.valid(current) !== null &&
    semver.gt(latest, current) &&
    (known?.skipped === undefined || semver.gt(latest, known.skipped));
  const notice = newer
    ? `${message("cli.updateAvailable", { latest, current })}${upgradeCommand ? ` ${message("cli.upgradeWith", { command: upgradeCommand })}` : ""}`
    : undefined;
  const due = !known || now() - known.checkedAt >= UPDATES.checkEveryMs;
  const refresh = due ? look(source, statePath, now, signal, latest) : Promise.resolve();
  return { ...(newer && notice ? { available: latest, notice } : {}), refresh };
}

/** Keep `version` as skipped: neither the prompt nor the notice shows until a newer release is found. */
export async function skipVersion(statePath: string, url: string, version: string): Promise<void> {
  const known = readState(statePath, url);
  await write(statePath, {
    url,
    checkedAt: known?.checkedAt ?? 0,
    ...(known?.latest ? { latest: known.latest } : {}),
    skipped: version,
  });
}

async function look(
  source: UpdateSource,
  statePath: string,
  now: () => number,
  signal: AbortSignal,
  before: string | undefined,
): Promise<void> {
  let latest = before;
  try {
    latest = await source.latest(AbortSignal.any([signal, AbortSignal.timeout(REQUEST_MS.updateCheck)]));
  } catch {
    if (signal.aborted) return;
  }
  // Read again now: a version skipped while the look ran is kept.
  const skipped = readState(statePath, source.url)?.skipped;
  await write(statePath, {
    url: source.url,
    checkedAt: now(),
    ...(latest ? { latest } : {}),
    ...(skipped ? { skipped } : {}),
  });
}

/** Written whole: to a file beside it, then moved into its place. Not written, the next start looks again. */
async function write(statePath: string, state: State): Promise<void> {
  try {
    await fs.mkdir(dirname(statePath), { recursive: true });
    await writeAtomic(statePath, JSON.stringify(state));
  } catch {
    // Not recorded.
  }
}

/** What an earlier check of this source found; anything unreadable counts as never checked. */
function readState(path: string, url: string): State | undefined {
  try {
    const state = JSON.parse(readFileSync(path, "utf8")) as Partial<State>;
    if (state.url !== url || typeof state.checkedAt !== "number") return undefined;
    const latest = typeof state.latest === "string" ? semver.valid(state.latest) : null;
    const skipped = typeof state.skipped === "string" ? semver.valid(state.skipped) : null;
    return {
      url,
      checkedAt: state.checkedAt,
      ...(latest ? { latest } : {}),
      ...(skipped ? { skipped } : {}),
    };
  } catch {
    return undefined;
  }
}
