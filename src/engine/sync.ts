// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Copying a session to Tauric, when the user has turned sync on (it is off unless set).
 * Tauric gets the session file's bytes as they are, whole lines only, at the offsets the file
 * has: after each turn's commit is on disk, the bytes up to that commit not yet confirmed are
 * appended. Each run of a session first checks Tauric's copy against the file, read-only; a
 * copy that differs is left alone and sync pauses for that session. Nothing here can fail a turn:
 * problems are reported and the next commit tries again.
 */

import { promises as fs } from "node:fs";
import { abortableSleep } from "../agents/recovery.js";
import { errorText, message, printable } from "../contracts/index.js";
import { SYNC } from "../contracts/limits.js";
import { DataError } from "../data/errors.js";

type Call = { signal?: AbortSignal };

/** A session the account holds, as its list describes it. */
export type RemoteSummary = { id: string; created: string; updated: Date; size: number; title: string };

/** The session storage operations sync uses (Tauric provides them). */
export type RemoteSessions = {
  readonly application: string;
  /** The account's sessions of this application, newest first, at most `limit`; changes nothing. */
  list(limit: number, call?: Call): Promise<RemoteSummary[]>;
  /** Whether Tauric keeps this application's sessions for the account; changes nothing. */
  accepts(call?: Call): Promise<boolean>;
  /** The session's size and metadata, or undefined when Tauric has none by this id; changes nothing. */
  describe(id: string, call?: Call): Promise<{ size: number; metadata?: Record<string, string> } | undefined>;
  /** Create the session, or replace its metadata whole. */
  putSession(id: string, metadata: Record<string, string>, call?: Call): Promise<unknown>;
  /** Delete the session; also fine for an id Tauric does not have. */
  deleteSession(id: string, call?: Call): Promise<void>;
  /** Bytes from `start` to `end` inclusive. */
  readSession(id: string, start: number, end: number, call?: Call): Promise<Uint8Array>;
  append(
    id: string,
    offset: number,
    lines: string,
    call?: Call,
  ): Promise<{ size: number; verifiedTo: number }>;
};

export type SyncOptions = {
  remote: RemoteSessions;
  /** The session file and its id (the remote session has the same id). */
  path: string;
  id: string;
  metadata: Record<string, string>;
  /** Whether sync is still on, asked before each request that sends; turning it off stops this session's sync. */
  stillOn?: () => Promise<boolean>;
  report: (problem: string) => void;
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
  drainMs?: number;
  stopWaitMs?: number;
};

export class SessionSync {
  private worker: Promise<void> | undefined;
  /** File bytes known to be committed, and the most an upload has tried to reach. */
  private limit = 0;
  private tried = 0;
  /** Remote bytes known to equal the file's; undefined until this run has checked Tauric's copy. */
  private acknowledged: number | undefined;
  private stopped = false;
  private readonly abort = new AbortController();
  constructor(private readonly options: SyncOptions) {}

  /** Upload the file up to byte `committed`, which is on disk; called after each commit and on resume. */
  schedule(committed: number): void {
    if (this.stopped) return;
    this.limit = Math.max(this.limit, committed);
    if (this.worker || this.tried >= this.limit) return;
    this.worker = this.work();
  }

  /** Wait a little for uploads under way, then cancel what is left and stop. */
  async close(): Promise<void> {
    await this.within(this.options.drainMs ?? SYNC.drainMs);
    this.stopped = true;
    this.abort.abort();
    // Cancelled requests end promptly; one that does not (a source that ignores it) is waited for only
    // so long, and sends nothing more: the worker is stopped.
    await this.within(this.options.stopWaitMs ?? SYNC.stopWaitMs);
  }

  /** Wait for the worker, at most `ms`. */
  private async within(ms: number): Promise<void> {
    if (!this.worker) return;
    let timer: NodeJS.Timeout | undefined;
    await Promise.race([this.worker, new Promise((resolve) => (timer = setTimeout(resolve, ms)))]);
    clearTimeout(timer);
  }

  /** One worker per session: passes until every committed byte has been tried. */
  private async work(): Promise<void> {
    try {
      while (!this.stopped && this.tried < this.limit) {
        const target = this.limit;
        await this.drain(target);
        this.tried = target;
      }
    } finally {
      this.worker = undefined;
    }
  }

  private stop(problem: string): void {
    this.stopped = true;
    this.options.report(problem);
  }

  private async drain(target: number): Promise<void> {
    const sleep = this.options.sleep ?? abortableSleep;
    for (let attempt = 0; ; attempt++) {
      try {
        await this.upload(target);
        return;
      } catch (error) {
        if (this.stopped || this.abort.signal.aborted) return;
        const transient =
          !(error instanceof DataError) || error.kind === "unavailable" || error.kind === "rate_limited";
        if (error instanceof DataError && (error.kind === "rejected" || error.kind === "quota")) {
          this.stop(
            message(error.kind === "quota" ? "sync.stoppedQuota" : "sync.stoppedKey", {
              reason: error.message,
            }),
          );
          return;
        }
        if (error instanceof DataError && error.kind === "full") {
          this.stop(message("sync.storageFull", { remainingBytes: error.details.remainingBytes }));
          return;
        }
        if (error instanceof DataError && (error.kind === "conflict" || error.kind === "diverged")) {
          this.stop(message("sync.paused", { reason: error.message }));
          return;
        }
        if (!transient) {
          this.stop(message("sync.refused", { reason: error.message }));
          return;
        }
        // Tauric's own advice on when to come back, when it gives one, over the schedule.
        const advised = error instanceof DataError ? (error.details.retryAfterMs ?? 0) : 0;
        const scheduled = SYNC.retryMs[attempt];
        const wait = scheduled === undefined ? undefined : Math.max(scheduled, advised);
        if (wait === undefined) {
          this.options.report(message("sync.unreachable", { reason: errorText(error) }));
          return;
        }
        try {
          await sleep(wait, this.abort.signal);
        } catch {
          return;
        }
      }
    }
  }

  /** One pass: check Tauric's copy once per run, then append the committed whole lines it lacks. */
  private async upload(target: number): Promise<void> {
    const { remote, path, id } = this.options;
    const call = { signal: this.abort.signal };
    const file = await fs.readFile(path);
    if (!(await this.stillOn())) return;
    // An account that does not keep this application's sessions has none to find or create: say so once.
    if (this.acknowledged === undefined) {
      if (!(await remote.accepts(call))) {
        this.stop(message("sync.notOffered", { app: remote.application }));
        return;
      }
      // Sync may have been turned off while the account was read.
      if (!(await this.stillOn())) return;
      const start = await this.remoteStart(file, call);
      if (start === undefined) return;
      this.acknowledged = start;
    }
    // Only committed whole lines are sent: the bytes up to the last newline within the commit.
    const end = file.subarray(0, Math.min(target, file.length)).lastIndexOf(0x0a) + 1;
    while (this.acknowledged < end) {
      const from = this.acknowledged;
      let chunkEnd = Math.min(end, from + SYNC.chunkBytes);
      if (chunkEnd < end) chunkEnd = file.lastIndexOf(0x0a, chunkEnd - 1) + 1;
      if (chunkEnd <= from) {
        this.stop(message("sync.lineTooLarge"));
        return;
      }
      const chunk = file.subarray(from, chunkEnd).toString("utf8");
      if (!(await this.stillOn())) return;
      let reached = chunkEnd;
      try {
        const { verifiedTo } = await remote.append(id, from, chunk, call);
        if (verifiedTo < chunkEnd) throw new Error(`Tauric confirmed ${verifiedTo} of ${chunkEnd} bytes`);
      } catch (error) {
        // Tauric is ahead of what was confirmed (an earlier append arrived unacknowledged, or
        // another writer): its extra bytes must be this file's, or the copies have diverged.
        const size = error instanceof DataError && error.kind === "conflict" ? error.details.size : undefined;
        if (size === undefined || size <= from || size > end) throw error;
        await this.verify(file, from, size, call);
        reached = size;
      }
      this.acknowledged = reached;
    }
  }

  /** Whether sync is still on; when it was turned off, stop, so nothing more is sent. */
  private async stillOn(): Promise<boolean> {
    if (this.stopped) return false;
    if (!this.options.stillOn || (await this.options.stillOn())) return true;
    this.stop(message("sync.turnedOff"));
    return false;
  }

  /**
   * Where uploading starts in this run: a session Tauric does not have is created at 0; one it
   * has is read, never changed, and must hold this file's first bytes. Undefined when sync was turned off.
   */
  private async remoteStart(file: Buffer, call: Call): Promise<number | undefined> {
    const { remote, id, metadata } = this.options;
    const found = await remote.describe(id, call);
    if (!found) {
      // Nothing is created once sync is off.
      if (!(await this.stillOn())) return undefined;
      const title = titleOf(file);
      await remote.putSession(id, title ? { ...metadata, title } : metadata, call);
      return 0;
    }
    if (found.size > file.length) {
      throw new DataError("diverged", "it holds more than this file", { source: "Tauric", size: found.size });
    }
    await this.verify(file, 0, found.size, call);
    // The copy's description follows the session (the model it runs on now, after a switch or a resume on
    // another): what this run says replaces what differs, and the rest (its title) is kept.
    const described = found.metadata ?? {};
    if (Object.entries(metadata).some(([key, value]) => described[key] !== value)) {
      if (!(await this.stillOn())) return undefined;
      await remote.putSession(id, { ...described, ...metadata }, call);
    }
    return found.size;
  }

  /** Tauric's bytes from `from` up to `to` must equal the file's. */
  private async verify(file: Buffer, from: number, to: number, call: Call): Promise<void> {
    if (to <= from) return;
    const remote = await this.options.remote.readSession(this.options.id, from, to - 1, call);
    if (!Buffer.from(remote).equals(file.subarray(from, to))) {
      throw new DataError("diverged", "its bytes do not match this file", { source: "Tauric", size: to });
    }
  }
}

/** The most of a session's first question kept as its title in the account's list. */
const TITLE_CHARS = 200;

/** The session's first question, on one printable line, for the account's list; "" when it has none. */
function titleOf(file: Buffer): string {
  for (const line of file.toString("utf8").split("\n")) {
    if (!line.includes('"turn.started"')) continue;
    try {
      const entry = JSON.parse(line) as {
        kind?: string;
        envelope?: { event?: { type?: string; question?: unknown } };
      };
      const event = entry.envelope?.event;
      if (entry.kind !== "event" || event?.type !== "turn.started" || typeof event.question !== "string")
        continue;
      const words = [...printable(event.question).replace(/\s+/g, " ").trim()];
      return words.length > TITLE_CHARS ? `${words.slice(0, TITLE_CHARS - 1).join("")}…` : words.join("");
    } catch {}
  }
  return "";
}
