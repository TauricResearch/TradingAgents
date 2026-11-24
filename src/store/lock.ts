// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * A lock file held by one process, naming its holder. It appears with its contents complete: they
 * are written to a private file first, which is then linked into place, and the link fails if a lock
 * is there. A lock whose holder was a process on this machine that no longer exists is stale, and so
 * is one whose process number now names another process: this one, when it does not hold the lock,
 * or (where the system tells when a process started) one started at another time. A stale lock is
 * removed only by the holder of a second lock beside it (`<path>.break`), after reading again that
 * it is still the stale holder's; nothing else ever moves or removes a lock it does not hold. A lock
 * from another machine, or one that cannot be read, is never taken. Release removes the file only if
 * it is still this holder's. Processes that share these files are taken to share one machine's
 * process numbers (one host, one process namespace).
 *
 * A breaker that crashed mid-takeover leaves its own lock stale. That one is never removed
 * automatically (removing it safely would need a breaker of its own): the lock stays unavailable and
 * `stuck` names the file to delete by hand. It takes a crash during a takeover after a crash.
 */
import { randomBytes } from "node:crypto";
import { constants, promises as fs } from "node:fs";
import { hostname } from "node:os";
import { dirname, join } from "node:path";

type Holder = { pid: number; host: string; token: string; started?: string };

/** The locks this process holds, by token. */
const HELD = new Set<string>();

export class Lock {
  private constructor(
    readonly path: string,
    private readonly token: string,
  ) {}

  /**
   * Take the lock at `path`, or return who holds it (no one named when the lock cannot be read), and
   * the left-over file to remove when a crashed takeover blocks it.
   */
  static async acquire(
    path: string,
  ): Promise<Lock | { heldBy?: { pid: number; host: string }; stuck?: string }> {
    await fs.mkdir(dirname(path), { recursive: true, mode: 0o700 });
    const token = randomBytes(12).toString("hex");
    const me = { pid: process.pid, host: hostname(), token, ...(await startedOf(process.pid)) };
    // Two tries: the second after removing a stale lock.
    for (let attempt = 0; attempt < 2; attempt++) {
      // Held from the moment it can appear, so this process never takes it for another's.
      HELD.add(token);
      if (await publish(path, me)) return new Lock(path, token);
      HELD.delete(token);
      const holder = await readHolder(path);
      if (!holder || !(await isStale(holder))) return heldBy(holder);
      const stuck = await breakStale(path, holder.token);
      if (stuck) return { ...heldBy(holder), stuck };
    }
    return heldBy(await readHolder(path));
  }

  private released: Promise<void> | undefined;

  /** Remove the lock if this holder still has it; releasing again does nothing more. */
  release(): Promise<void> {
    this.released ??= removeIfStill(this.path, this.token).finally(() => HELD.delete(this.token));
    return this.released;
  }
}

/** Put a lock with `holder` at `path` unless one is there; true when it was put. */
async function publish(path: string, holder: Holder): Promise<boolean> {
  const draft = join(dirname(path), `.${holder.token}.draft`);
  const handle = await fs.open(draft, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL, 0o600);
  try {
    await handle.writeFile(JSON.stringify(holder));
    await handle.close();
    try {
      await fs.link(draft, path);
      return true;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "EEXIST") return false;
      throw error;
    }
  } finally {
    await handle.close().catch(() => {});
    await fs.rm(draft, { force: true });
  }
}

/** Remove the lock at `path` if its holder's token is still `token`; only that holder or a breaker calls this. */
async function removeIfStill(path: string, token: string): Promise<void> {
  if ((await readHolder(path))?.token === token) await fs.rm(path, { force: true });
}

/**
 * Remove the stale lock at `path` (holder `token`) while holding its breaker lock; any change and it
 * is left. Returns the breaker's path when a crashed breaker blocks the takeover.
 */
async function breakStale(path: string, token: string): Promise<string | undefined> {
  const breaker = `${path}.break`;
  const me = {
    pid: process.pid,
    host: hostname(),
    token: randomBytes(12).toString("hex"),
    ...(await startedOf(process.pid)),
  };
  HELD.add(me.token);
  if (!(await publish(breaker, me))) {
    HELD.delete(me.token);
    // Another process is breaking it, or one that crashed doing so left its breaker behind.
    const other = await readHolder(breaker);
    return other && (await isStale(other)) ? breaker : undefined;
  }
  try {
    await removeIfStill(path, token);
  } finally {
    await removeIfStill(breaker, me.token);
    HELD.delete(me.token);
  }
  return undefined;
}

function heldBy(holder: Holder | undefined): { heldBy?: { pid: number; host: string } } {
  return holder ? { heldBy: { pid: holder.pid, host: holder.host } } : {};
}

async function readHolder(path: string): Promise<Holder | undefined> {
  try {
    const value = JSON.parse(await fs.readFile(path, "utf8")) as Partial<Holder>;
    if (typeof value.pid === "number" && typeof value.host === "string" && typeof value.token === "string")
      return {
        pid: value.pid,
        host: value.host,
        token: value.token,
        ...(typeof value.started === "string" ? { started: value.started } : {}),
      };
  } catch {
    // Missing or unreadable.
  }
  return undefined;
}

async function isStale(holder: Holder): Promise<boolean> {
  if (holder.host !== hostname()) return false;
  // This process's own number: another lock by it is one left by an earlier process that had the
  // number, unless the start times say it is this one (where they are known).
  if (holder.pid === process.pid) {
    if (HELD.has(holder.token)) return false;
    const mine = (await startedOf(process.pid)).started;
    return holder.started === undefined || mine === undefined || holder.started !== mine;
  }
  try {
    process.kill(holder.pid, 0);
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "ESRCH";
  }
  // Alive: the holder only if it started when the lock says (when both times are known).
  const now = (await startedOf(holder.pid)).started;
  return holder.started !== undefined && now !== undefined && now !== holder.started;
}

/** When a process started, in the system's ticks since boot, where the system says (Linux). */
async function startedOf(pid: number): Promise<{ started?: string }> {
  try {
    const stat = await fs.readFile(`/proc/${pid}/stat`, "utf8");
    // The fields after the command name (in parentheses, and it may hold spaces): the 20th is the start.
    const started = stat.slice(stat.lastIndexOf(")") + 2).split(" ")[19];
    return started ? { started } : {};
  } catch {
    return {};
  }
}
