// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Sessions in the Tauric account that are not on this computer: listed beside the local ones, and copied
 * here when one is opened, after which it resumes and syncs as any session. There is no merge: a session on
 * both is the local one, and sync pauses for it when the two differ. A copy is checked whole (the account's
 * size, whole lines, its own header) before it becomes a session; a copy cut short never does.
 */

import { constants, promises as fs } from "node:fs";
import { errorText, message } from "../contracts/index.js";
import { SESSIONS, SYNC } from "../contracts/limits.js";
import { SESSION_ID } from "./engine.js";
import {
  downloadOf,
  fileOf,
  listSessions,
  pendingDeletions,
  SessionError,
  type SessionSummary,
  sessionsDir,
  takeLock,
} from "./session.js";
import type { RemoteSessions } from "./sync.js";

type Call = { signal?: AbortSignal };

/**
 * The sessions here and, through `remote` (sync on with a Tauric key), those only in the account, newest
 * first, at most `limit`. The account's are marked `where: "account"`. When the account cannot be listed,
 * the sessions here, with the problem in words.
 */
export async function allSessions(
  dir: string,
  remote: Pick<RemoteSessions, "list"> | undefined,
  { limit = SESSIONS.listed as number, signal }: { limit?: number } & Call = {},
): Promise<{ sessions: SessionSummary[]; problem?: string }> {
  const here = await listSessions(dir, { limit });
  if (!remote) return { sessions: here };
  let listed: Awaited<ReturnType<RemoteSessions["list"]>>;
  try {
    listed = await remote.list(limit, signal ? { signal } : {});
  } catch (error) {
    return { sessions: here, problem: message("sync.listFailed", { reason: errorText(error) }) };
  }
  // A session here is the one shown; one being deleted from the account is gone already.
  const known = new Set(await pendingDeletions(dir));
  const local = new Set(
    (await fs.readdir(sessionsDir(dir)).catch(() => [] as string[])).map((name) =>
      name.replace(/\.jsonl$/, ""),
    ),
  );
  const away = listed
    .filter((one) => SESSION_ID.test(one.id) && !known.has(one.id) && !local.has(one.id) && one.size > 0)
    .map(
      (one): SessionSummary => ({
        id: one.id,
        created: one.created,
        updated: one.updated,
        title: one.title,
        turns: 0,
        where: "account",
      }),
    );
  const sessions = [...here, ...away]
    .sort((a, b) => b.updated.getTime() - a.updated.getTime())
    .slice(0, limit);
  return { sessions };
}

/** Whether session `id` is on this computer. */
export async function isHere(dir: string, id: string): Promise<boolean> {
  return fs.access(fileOf(dir, id)).then(
    () => true,
    () => false,
  );
}

/**
 * Copy session `id` from the account to this computer, unless it is here already (the one here is kept).
 * The copy is read in ranges to the size the account states, checked (that size exactly, whole lines that
 * each parse, a session header with this id) and only then put in place; a check that fails leaves nothing.
 */
export async function download(
  dir: string,
  id: string,
  remote: Pick<RemoteSessions, "describe" | "readSession">,
  call: Call = {},
): Promise<"downloaded" | "here"> {
  if (!SESSION_ID.test(id)) throw new SessionError(message("session.badId", { id }));
  if (await isHere(dir, id)) return "here";
  // One being deleted from the account is gone already, though Tauric may still have it.
  if ((await pendingDeletions(dir)).includes(id)) throw new SessionError(message("session.missing", { id }));
  const found = await remote.describe(id, call);
  if (!found || found.size === 0) throw new SessionError(message("session.missing", { id }));
  await fs.mkdir(sessionsDir(dir), { recursive: true, mode: 0o700 });
  const lock = await takeLock(dir, id);
  // Hidden and not a session file name: never listed, and replaced by the next download of the id.
  const temporary = downloadOf(dir, id);
  try {
    if (await isHere(dir, id)) return "here";
    if ((await pendingDeletions(dir)).includes(id))
      throw new SessionError(message("session.missing", { id }));
    await fs.rm(temporary, { force: true });
    const bytes = await readWhole(id, found.size, remote, call);
    checkCopy(id, bytes);
    const handle = await fs.open(temporary, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL, 0o600);
    try {
      await handle.writeFile(bytes);
      await handle.sync();
    } finally {
      await handle.close();
    }
    try {
      // A link, not a rename: it fails when a session file appeared meanwhile, which is then the one kept.
      await fs.link(temporary, fileOf(dir, id));
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "EEXIST") return "here";
      throw error;
    }
    await syncFolder(sessionsDir(dir));
    return "downloaded";
  } finally {
    await fs.rm(temporary, { force: true }).catch(() => {});
    await lock.release();
  }
}

/** The account's `size` bytes of session `id`, in ranges of at most `SYNC.chunkBytes`, each as long as asked. */
async function readWhole(
  id: string,
  size: number,
  remote: Pick<RemoteSessions, "readSession">,
  call: Call,
): Promise<Buffer> {
  const parts: Buffer[] = [];
  for (let from = 0; from < size; ) {
    const to = Math.min(size, from + SYNC.chunkBytes);
    const part = Buffer.from(await remote.readSession(id, from, to - 1, call));
    if (part.length !== to - from) {
      throw new SessionError(message("sync.copyIncomplete", { id, got: from + part.length, size }));
    }
    parts.push(part);
    from = to;
  }
  return Buffer.concat(parts, size);
}

/** A copy is whole lines that each parse, the first a session header with this id. */
function checkCopy(id: string, bytes: Buffer): void {
  const text = bytes.toString("utf8");
  if (!text.endsWith("\n")) throw new SessionError(message("sync.copyDamaged", { id, line: 0 }));
  const lines = text.slice(0, -1).split("\n");
  for (const [index, line] of lines.entries()) {
    let value: unknown;
    try {
      value = JSON.parse(line);
    } catch {
      throw new SessionError(message("sync.copyDamaged", { id, line: index + 1 }));
    }
    if (index === 0) {
      const header = value as { kind?: unknown; id?: unknown } | null;
      if (header?.kind !== "session" || header.id !== id)
        throw new SessionError(message("sync.copyNotThis", { id }));
    }
  }
}

/** Make a folder's entries durable (a new name in it); not offered on every system, so best effort. */
async function syncFolder(path: string): Promise<void> {
  const handle = await fs.open(path, "r").catch(() => undefined);
  await handle?.sync().catch(() => {});
  await handle?.close().catch(() => {});
}
