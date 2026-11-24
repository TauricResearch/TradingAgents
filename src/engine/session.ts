// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Sessions on disk: one append-only file per session, so a conversation can be resumed and read
 * back. The file holds the events as the reader saw them (finished text, no reasoning) and, when a
 * turn ends, one commit entry saying how the conversation changed. Resume rebuilds the conversation
 * from the commits alone, so a turn that never ended (a crash) is shown but not carried on.
 */

import { promises as fs } from "node:fs";
import { hostname } from "node:os";
import { join } from "node:path";
import { SESSIONS_DIR } from "../config/index.js";
import {
  type EventEnvelope,
  errorText,
  type Message,
  message,
  NOTICE,
  type RouteName,
  withoutReplay,
} from "../contracts/index.js";
import { SESSIONS } from "../contracts/limits.js";
import {
  DamagedLogError,
  Lock,
  LogWriter,
  readLog,
  readLogHead,
  readPrivate,
  writePrivate,
} from "../store/index.js";
import {
  type EvidenceRecord,
  type EvidenceRow,
  EvidenceStore,
  type RestoredEvidence,
  restoreEvidence,
} from "../tools/evidence-store.js";
import type { RunRecord } from "./delegation.js";
import {
  type AskOptions,
  type Engine,
  EventQueue,
  newSessionId,
  type RestoredState,
  SESSION_ID,
  type Turn,
} from "./engine.js";
import { type RemoteSessions, SessionSync, type SyncOptions } from "./sync.js";

type Header = { kind: "session"; id: string; created: string };
type TurnEntry = {
  kind: "turn";
  turn: string;
  /** The model that ran the turn. */
  model: string;
  /** Its route, to resume on (no key or address). */
  route?: RouteName;
  /**
   * Who the data a provider attached in this turn may be sent back to (provider, endpoint and model);
   * a turn without one sends none.
   */
  replayKey?: string;
  status: string;
  replaced?: Message[];
  added: Message[];
  tokens?: number;
  runs: RunRecord[];
};
/** The model the session runs on from here: the next turn's, and the one to resume on. */
type ModelEntry = {
  kind: "model";
  route: RouteName;
  /** Who the model's replay data may be sent back to: what another model attached before is not. */
  replayKey?: string;
  at: string;
};
type Entry = { kind: "event"; envelope: EventEnvelope } | TurnEntry | ModelEntry | EvidenceRow;

/** A session as a list shows it; `turns` counts the turns it committed. */
export type SessionSummary = {
  id: string;
  created: string;
  updated: Date;
  title: string;
  turns: number;
  /** Only in the Tauric account, not on this computer yet (its turns are not counted). */
  where?: "account";
};

/** Copying the session to Tauric, when sync is on: where to, what must never be sent, and whether it still is on. */
export type SyncSetup = Pick<SyncOptions, "remote" | "metadata" | "stillOn">;

/** Builds the session's engine: a new one, or one continuing where the file left off. */
export type EngineBuilder = (init: {
  session: string;
  restore?: RestoredState;
  /** The session's recorded results, written to its file as they are published. */
  evidence?: EvidenceStore;
}) => Engine;

/** A model for the session to run on from its next question: the engine it builds, and its route. */
type ModelSwitch = {
  build: EngineBuilder;
  route: RouteName;
  /** Who the new model's replay data may be sent back to; what another model attached is not sent to it. */
  replayKey: string | undefined;
  /** Where the session is copied, when the switch brings a Tauric key and sync is on. */
  sync?: SyncSetup;
};

export class SessionError extends Error {
  override readonly name = "SessionError";
}

export class Session {
  private writes: Promise<void> = Promise.resolve();
  private failed = false;
  /** A payload could not be kept on this computer (said once). */
  private unkept = false;
  private sync: SessionSync | undefined;
  /** The turn running, if one is: a model switch waits for it to end. */
  private running: object | undefined;
  /** The copy most recently asked for, by a switch that brought a key. */
  private wantedSync: SyncSetup | undefined;
  /** The model switched to while a turn ran, taken up when it ends. */
  private next: ModelSwitch | undefined;

  private constructor(
    readonly id: string,
    private current: Engine,
    /** The session's recorded results, which an engine that takes over keeps publishing to. */
    private readonly evidence: EvidenceStore,
    /** The file and its lock; both absent when the session could not be saved from the start. */
    private readonly log: LogWriter | undefined,
    private readonly lock: Lock | undefined,
    /** Events of the last turns, to show again; `interrupted` when the last turn never ended. */
    readonly replay: { events: EventEnvelope[]; interrupted: boolean },
    /** Problems to show the user (a repaired file, a write that failed). */
    private readonly report: (problem: string) => void,
  ) {}

  /** A new session; if it cannot be saved, it runs unsaved and says so once. */
  static async start(
    dir: string,
    build: EngineBuilder,
    report: (problem: string) => void,
    sync?: SyncSetup,
  ): Promise<Session> {
    const id = newSessionId();
    let lock: Lock | undefined;
    let log: LogWriter | undefined;
    try {
      lock = await takeLock(dir, id);
      const header: Header = { kind: "session", id, created: new Date().toISOString() };
      log = await LogWriter.open(fileOf(dir, id), header);
    } catch (error) {
      await log?.close().catch(() => {});
      await lock?.release().catch(() => {});
      log = undefined;
      lock = undefined;
      report(message("session.unsaved", { reason: errorText(error) }));
    }
    try {
      // Records reach the file through the session's write queue, ahead of their turn's commit.
      let session: Session | undefined;
      const evidence = new EvidenceStore(
        (rows) => session?.write(rows),
        undefined,
        (record, payload) => session?.keep(keptOf(dir, id), record, payload),
      );
      session = new Session(
        id,
        build({ session: id, evidence }),
        evidence,
        log,
        lock,
        { events: [], interrupted: false },
        report,
      ).syncing(sync);
      return session;
    } catch (error) {
      await log?.close().catch(() => {});
      await lock?.release().catch(() => {});
      throw error;
    }
  }

  /**
   * Continue session `id` with an engine whose model has `replayKey`; refuses one open elsewhere or
   * damaged.
   */
  static async resume(
    dir: string,
    id: string,
    replayKey: string | undefined,
    build: EngineBuilder,
    report: (problem: string) => void,
    sync?: SyncSetup,
  ): Promise<Session> {
    if (!SESSION_ID.test(id)) throw new SessionError(message("session.badId", { id }));
    const path = fileOf(dir, id);
    try {
      await fs.access(path);
    } catch {
      throw new SessionError(message("session.missing", { id }));
    }
    const lock = await takeLock(dir, id);
    let log: LogWriter | undefined;
    try {
      // Checked before opening for append, which would cut a torn header away.
      const [header] = (await readLogHead(path)) as [Header | null | undefined];
      if (typeof header !== "object" || header === null || header.kind !== "session")
        throw new SessionError(message("session.damaged", { id, line: 1 }));
      log = await LogWriter.open(path);
      if (log.repairedBytes) report(message("session.repaired", { id }));
      let values: unknown[];
      try {
        values = await readLog(path);
      } catch (error) {
        throw error instanceof DamagedLogError
          ? new SessionError(message("session.damaged", { id, line: error.line }))
          : error;
      }
      const rest = values.slice(1) as Entry[];
      const { restore, replay, evidence: kept, inForce } = restored(rest, replayKey);
      await readKept(keptOf(dir, id), kept.records);
      let session: Session | undefined;
      const evidence = new EvidenceStore(
        (rows) => session?.write(rows),
        kept,
        (record, payload) => session?.keep(keptOf(dir, id), record, payload),
      );
      session = new Session(
        id,
        build({ session: id, restore, evidence }),
        evidence,
        log,
        lock,
        replay,
        report,
      ).syncing(sync);
      // Resumed on another model than the one it went on with: kept as a switch, so a later switch back
      // does not bring back what this one is not sent. On file before the session is given, so a reader
      // of the file then sees the model it resumed on.
      const route = session.current.route;
      if (route && replayKey !== inForce) {
        const entry: ModelEntry = {
          kind: "model",
          route,
          ...(replayKey !== undefined ? { replayKey } : {}),
          at: new Date().toISOString(),
        };
        session.write([entry]);
        await session.writes;
      }
      session.catchUp();
      return session;
    } catch (error) {
      await log?.close().catch(() => {});
      await lock.release().catch(() => {});
      throw error;
    }
  }

  /** The engine the session's next turn runs on. */
  get engine(): Engine {
    return this.current;
  }

  /**
   * Run on another model from the next question, and resume on it: at once between turns, else once the
   * running turn ends on its own model. The conversation goes on as it is; what the earlier model
   * attached for itself is not sent to another, and the history's size is counted afresh.
   */
  switchTo(next: ModelSwitch): void {
    this.next = next;
    this.takeUp();
  }

  /**
   * The engine of the model switched to, taking over where the current one stands, once no turn runs.
   * The change is kept at once and copied with the session, so it resumes on the model switched to.
   */
  private takeUp(asking = false): void {
    const next = this.next;
    // A question asked takes it up as soon as the engine is free, though the turn before is still being kept.
    if (!next || (this.running && !asking)) return;
    // Read first: an engine still busy keeps the switch waiting.
    const { history, historyTokens, ...counters } = this.current.state();
    this.next = undefined;
    const same = next.replayKey !== undefined && next.replayKey === this.current.replayKey;
    const restore = same
      ? { history, ...(historyTokens !== undefined ? { historyTokens } : {}), ...counters }
      : { history: history.map((message) => withoutReplay(message)), ...counters };
    this.current = next.build({ session: this.id, restore, evidence: this.evidence });
    // The copy changes first, so the change is not sent where the session is no longer copied.
    if (next.sync) this.syncWith(next.sync);
    const entry: ModelEntry = {
      kind: "model",
      route: next.route,
      ...(next.replayKey !== undefined ? { replayKey: next.replayKey } : {}),
      at: new Date().toISOString(),
    };
    this.write([entry], (size) => this.sync?.schedule(size));
  }

  /**
   * Copy the session through `setup`, from its start: sync turned on while it runs, or a key saved since
   * that may be another account's, so the copy that ran goes on no further once its last upload has ended.
   * Of several asked, the last wins.
   */
  syncWith(setup: SyncSetup): void {
    this.wantedSync = setup;
    this.writes = this.writes.then(async () => {
      if (this.wantedSync !== setup) return;
      const running = this.sync;
      this.sync = undefined;
      await running?.close().catch(() => {});
      this.syncing(setup);
      // Everything written meanwhile goes with the new copy.
      this.catchUp();
    });
  }

  /** A turn has ended: a model switched to while it ran takes over now. */
  private ended(turn: object): void {
    if (this.running !== turn) return;
    this.running = undefined;
    try {
      this.takeUp();
    } catch (error) {
      this.report(message("session.switchFailed", { reason: errorText(error) }));
    }
  }

  /**
   * Ask through the engine. The session reads the turn's events itself, so everything is recorded
   * whether or not the caller reads them, and the turn is committed once its last event is written.
   * Leaving the events early cancels the turn, as with the engine.
   */
  ask(question: string, options?: AskOptions): Turn {
    this.takeUp(true);
    const engine = this.current;
    const turn = engine.ask(question, options);
    const running = {};
    this.running = running;
    const coalesce = new TextCoalescer();
    const events = new EventQueue(() => turn.cancel());
    const record = (envelopes: EventEnvelope[]) =>
      this.write(envelopes.map((envelope) => ({ kind: "event", envelope })));
    const pumped = (async () => {
      try {
        for await (const envelope of turn.events) {
          record(coalesce.add(envelope));
          events.push(envelope);
        }
      } finally {
        record(coalesce.flush());
        events.close();
      }
    })();
    // A model switched to while the turn ran takes over once it has ended, however it ended: before its
    // outcome is given, so the switch is kept with the turn and anyone told of the end asks on it.
    const outcome = Promise.all([turn.outcome, pumped]).then(
      async ([result]) => {
        const commit: TurnEntry = {
          kind: "turn",
          turn: turn.id,
          model: engine.model,
          ...(engine.route ? { route: engine.route } : {}),
          ...(engine.replayKey !== undefined ? { replayKey: engine.replayKey } : {}),
          status: result.status,
          ...result.history,
          runs: result.runs.map((run) => ({ ...run, messages: withoutReasoning(run.messages) })),
        };
        this.write([commit], (size) => this.sync?.schedule(size));
        this.ended(running);
        await this.writes;
        return result;
      },
      async (error: unknown) => {
        this.ended(running);
        await this.writes;
        throw error;
      },
    );
    return { id: turn.id, events, outcome, cancel: turn.cancel };
  }

  async close(): Promise<void> {
    // Every write, those queued while waiting too (a copy started late catches up with one).
    for (let waited: Promise<void> | undefined; waited !== this.writes; ) {
      waited = this.writes;
      await waited;
    }
    await this.sync?.close();
    await this.log?.close().catch(() => {});
    await this.lock?.release();
  }

  /**
   * Keep a record's payload on this computer, in `folder`, queued ahead of the record's rows: a crash
   * leaves at most a payload no record names. Nothing is kept for a session that is not saved; a payload
   * that cannot be written is said once, and the session goes on saving with the record's preview.
   */
  private keep(folder: string, record: string, payload: unknown): void {
    if (!this.log) return;
    this.writes = this.writes.then(async () => {
      if (this.failed) return;
      try {
        await writePrivate(join(folder, `${record}.json`), JSON.stringify(payload));
      } catch (error) {
        if (!this.unkept) this.report(message("session.payloadNotKept", { reason: errorText(error) }));
        this.unkept = true;
      }
    });
  }

  /** Start copying to Tauric, for a session that is saved. */
  private syncing(setup: SyncSetup | undefined): this {
    if (setup && this.log) {
      this.sync = new SessionSync({ ...setup, path: this.log.path, id: this.id, report: this.report });
    }
    return this;
  }

  /**
   * Catch up on what an earlier run of the session did not send. A crash can leave a turn's rows after
   * its last commit that were never made durable, so the file is made durable before any is sent; a
   * failure is reported as a write's is.
   */
  private catchUp(): void {
    const log = this.log;
    if (!log || !this.sync) return;
    this.writes = this.writes.then(async () => {
      if (this.failed) return;
      try {
        await log.sync();
        this.sync?.schedule(await log.size());
      } catch (error) {
        this.failed = true;
        this.report(message("session.noLongerSaved", { reason: errorText(error) }));
      }
    });
  }

  /**
   * Queue a write; the first failure is reported once and recording stops. With `committed`, the
   * write is made durable and the file's size then is passed on (only that much is ever synced).
   */
  private write(entries: unknown[], committed?: (size: number) => void): void {
    const log = this.log;
    if (!log || !entries.length) return;
    this.writes = this.writes.then(async () => {
      if (this.failed) return;
      try {
        await log.append(...entries);
        if (committed) {
          await log.sync();
          committed(await log.size());
        }
      } catch (error) {
        this.failed = true;
        this.report(message("session.noLongerSaved", { reason: errorText(error) }));
      }
    });
  }
}

/** Sessions in `dir`, newest first. */
export async function listSessions(
  dir: string,
  { limit = SESSIONS.listed as number }: { limit?: number } = {},
): Promise<SessionSummary[]> {
  const folder = sessionsDir(dir);
  let names: string[];
  try {
    names = (await fs.readdir(folder)).filter(
      (name) => name.endsWith(".jsonl") && SESSION_ID.test(name.slice(0, -".jsonl".length)),
    );
  } catch {
    return [];
  }
  const stats = await Promise.allSettled(
    names.map(async (name) => ({ name, mtime: (await fs.stat(join(folder, name))).mtime })),
  );
  const files = stats.flatMap((result) => (result.status === "fulfilled" ? [result.value] : []));
  const summaries: SessionSummary[] = [];
  for (const file of files.sort((a, b) => b.mtime.getTime() - a.mtime.getTime())) {
    if (summaries.length >= limit) break;
    const [header, ...entries] = (await readLogHead(join(folder, file.name))) as [Header, ...Entry[]];
    if (header?.kind !== "session") continue;
    // A line that is not an entry (null, a number) is passed over.
    const asked = entries.find(
      (e) =>
        typeof e === "object" &&
        e !== null &&
        e.kind === "event" &&
        e.envelope?.event?.type === "turn.started",
    );
    const title =
      asked?.kind === "event" && asked.envelope.event.type === "turn.started"
        ? asked.envelope.event.question
        : "";
    // Each committed turn is one line that starts as its entry does.
    const text = await fs.readFile(join(folder, file.name), "utf8").catch(() => "");
    const turns = text.match(/^\{"kind":"turn"/gm)?.length ?? 0;
    summaries.push({ id: header.id, created: header.created, updated: file.mtime, title, turns });
  }
  return summaries;
}

/**
 * The route session `id` runs on: the last one a turn ran on or a switch chose, if it recorded one;
 * undefined for a session it cannot read.
 */
export async function savedRoute(dir: string, id: string): Promise<RouteName | undefined> {
  if (!SESSION_ID.test(id)) return undefined;
  try {
    const values = await readLog(fileOf(dir, id));
    const routed = (values.slice(1) as Entry[]).filter(
      (entry): entry is TurnEntry | ModelEntry =>
        (entry?.kind === "turn" || entry?.kind === "model") && entry.route !== undefined,
    );
    return routed.at(-1)?.route;
  } catch {
    return undefined;
  }
}

/** Where the sessions of home directory `dir` are kept. */
export function sessionsDir(dir: string): string {
  return join(dir, SESSIONS_DIR);
}

/** Where an account deletion waits until Tauric confirms it: the session ids, one list. */
function pendingFile(dir: string): string {
  return join(sessionsDir(dir), "deleting.json");
}

export async function pendingDeletions(dir: string): Promise<string[]> {
  try {
    const parsed: unknown = JSON.parse((await readPrivate(pendingFile(dir))) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}

async function setPending(dir: string, change: (ids: string[]) => string[]): Promise<void> {
  const ids = [...new Set(change(await pendingDeletions(dir)))];
  if (ids.length || (await readPrivate(pendingFile(dir)).catch(() => undefined)) !== undefined) {
    await writePrivate(pendingFile(dir), `${JSON.stringify(ids)}\n`);
  }
}

/**
 * Where a deletion took effect: here and in the account, here only (no account copy), here with the
 * account's pending, or (a session only in the account) there, or pending there.
 */
export type Deleted = "everywhere" | "here" | "pending" | "account" | "accountPending";

/**
 * Delete session `id`: here, and from the account through `remote` when sync copies sessions there. A
 * session open anywhere is not deleted. The account deletion is kept before the file goes, and sent again
 * later when Tauric cannot be reached now: "everywhere", "here" (no account copy), or "pending".
 */
export async function deleteSession(
  dir: string,
  id: string,
  remote?: Pick<RemoteSessions, "deleteSession" | "describe">,
): Promise<Deleted> {
  if (!SESSION_ID.test(id)) throw new SessionError(message("session.badId", { id }));
  const path = fileOf(dir, id);
  try {
    await fs.access(path);
  } catch {
    // A session only in the account is deleted there, once the account is known to have it: Tauric takes
    // a deletion of any id, so a mistyped one would otherwise read as deleted.
    if (!remote) throw new SessionError(message("session.missing", { id }));
    let found: { size: number } | undefined;
    try {
      found = await remote.describe(id);
    } catch (error) {
      throw new SessionError(message("sync.deleteUnconfirmed", { id, reason: errorText(error) }));
    }
    if (!found) throw new SessionError(message("session.missing", { id }));
    // Held as a download holds it, so none copies it here while it is being deleted.
    const lock = await takeLock(dir, id);
    try {
      await setPending(dir, (ids) => [...ids, id]);
    } finally {
      await lock.release();
    }
    return (await sendDeletion(dir, id, remote)) === "everywhere" ? "account" : "accountPending";
  }
  const lock = await takeLock(dir, id);
  try {
    if (remote) await setPending(dir, (ids) => [...ids, id]);
    // The kept payloads first: a deletion cut short leaves the session listed, to delete again.
    await fs.rm(keptOf(dir, id), { recursive: true, force: true });
    // A copy from the account a crash left beside the file holds the same data.
    await fs.rm(downloadOf(dir, id), { force: true });
    await fs.rm(path);
  } finally {
    await lock.release();
  }
  if (!remote) return "here";
  return sendDeletion(dir, id, remote);
}

/** Delete `id` from the account, kept pending when Tauric cannot be reached now. */
async function sendDeletion(
  dir: string,
  id: string,
  remote: Pick<RemoteSessions, "deleteSession">,
): Promise<"everywhere" | "pending"> {
  try {
    await remote.deleteSession(id);
    await setPending(dir, (ids) => ids.filter((pending) => pending !== id));
    return "everywhere";
  } catch {
    return "pending";
  }
}

/** Send the account deletions that could not be sent before; those that fail again wait for next time. */
export async function sendPendingDeletions(
  dir: string,
  remote: Pick<RemoteSessions, "deleteSession">,
): Promise<void> {
  for (const id of await pendingDeletions(dir)) {
    try {
      await remote.deleteSession(id);
      await setPending(dir, (ids) => ids.filter((pending) => pending !== id));
    } catch {
      // Kept for the next run.
    }
  }
}

/** Where a copy from the account is written before it becomes session `id`: hidden, never listed. */
export function downloadOf(dir: string, id: string): string {
  return join(sessionsDir(dir), `.${id}.download.tmp`);
}

export function fileOf(dir: string, id: string): string {
  return join(sessionsDir(dir), `${id}.jsonl`);
}

/**
 * The payloads kept on this computer for the restored records that stay here, read into them; one that
 * cannot be read leaves its record with its preview only, as on another computer.
 */
async function readKept(folder: string, records: EvidenceRecord[]): Promise<void> {
  for (const record of records) {
    if (!record.local_only) continue;
    const text = await readPrivate(join(folder, `${record.id}.json`)).catch(() => undefined);
    if (text === undefined) continue;
    try {
      record.payload = JSON.parse(text);
    } catch {
      // A file cut short is read as missing.
    }
  }
}

/** Where session `id` keeps the payloads that stay on this computer, a file per record; never synced. */
function keptOf(dir: string, id: string): string {
  return join(sessionsDir(dir), `${id}.local`);
}

export async function takeLock(dir: string, id: string): Promise<Lock> {
  const path = join(sessionsDir(dir), `${id}.lock`);
  const lock = await Lock.acquire(path);
  if (lock instanceof Lock) return lock;
  if (lock.stuck) {
    throw new SessionError(message("session.lockStuck", { id, path: lock.stuck }));
  }
  if (!lock.heldBy) throw new SessionError(message("session.lockUnreadable", { id, path }));
  if (lock.heldBy.host !== hostname()) {
    throw new SessionError(message("session.openOnHost", { id, path, ...lock.heldBy }));
  }
  throw new SessionError(message("session.openElsewhere", { id, pid: lock.heldBy.pid }));
}

/**
 * The conversation and counters the commits add up to, and the events of the last turns. Data a
 * provider attached for itself is kept only in what was written under the same replay key.
 */
function restored(
  entries: Entry[],
  replayKey: string | undefined,
): {
  restore: RestoredState;
  replay: Session["replay"];
  evidence: RestoredEvidence;
  /** The replay key the conversation last went on with: its last turn's, or switch's. */
  inForce: string | undefined;
} {
  let history: Message[] = [];
  const evidenceRows: EvidenceRow[] = [];
  const committed = new Set<string>();
  let historyTokens: number | undefined;
  let seq = 0;
  let turns = 0;
  let nudged = false;
  /** The replay key the conversation went on with last: a turn's, or a switch's. */
  let inForce: string | undefined;
  const events: EventEnvelope[] = [];
  const turnNumber = (id: string | undefined) => Number(id?.slice(1) ?? 0) || 0;
  for (const entry of entries) {
    if (entry.kind === "evidence" || entry.kind === "evidence.part") {
      evidenceRows.push(entry);
      continue;
    }
    if (entry.kind === "model") {
      // Switched to another model, the conversation went on without what the earlier one attached.
      if (entry.replayKey === undefined || entry.replayKey !== inForce) {
        history = history.map((message) => withoutReplay(message));
        historyTokens = undefined;
      }
      inForce = entry.replayKey;
      continue;
    }
    if (entry.kind === "turn") {
      committed.add(entry.turn);
      inForce = entry.replayKey;
      const forModel = (messages: Message[]) =>
        replayKey !== undefined && entry.replayKey === replayKey
          ? messages
          : messages.map((message) => withoutReplay(message));
      if (entry.replaced) history = forModel(entry.replaced);
      history = [...history, ...forModel(entry.added)];
      // The size the model last measured, unless the history changed after it in a way it did not see.
      if (entry.tokens !== undefined) historyTokens = entry.tokens;
      else if (entry.replaced || entry.added.length) historyTokens = undefined;
      // Written for another model: what it was measured with is not what is sent now.
      if (replayKey === undefined || entry.replayKey !== replayKey) historyTokens = undefined;
      turns = Math.max(turns, turnNumber(entry.turn));
      continue;
    }
    const { envelope } = entry;
    events.push(envelope);
    // Folded from every recorded event, not only the turns shown again or committed.
    if (envelope.event.type === "notice" && envelope.event.code === NOTICE.capabilityUnavailable)
      nudged = true;
    seq = Math.max(seq, envelope.seq + 1);
    turns = Math.max(turns, turnNumber(envelope.turn));
  }
  const ids = [...new Set(events.map((e) => e.turn).filter((t): t is string => t !== undefined))];
  const shown = new Set(ids.slice(-SESSIONS.replayTurns));
  const replay = events.filter((e) => e.turn === undefined || shown.has(e.turn));
  const lastTurn = ids.at(-1);
  const interrupted =
    lastTurn !== undefined &&
    !events.some(
      (e) =>
        e.turn === lastTurn &&
        (e.event.type === "turn.completed" ||
          e.event.type === "turn.cancelled" ||
          e.event.type === "turn.failed"),
    );
  return {
    restore: {
      history,
      seq,
      turns,
      ...(historyTokens !== undefined ? { historyTokens } : {}),
      ...(nudged ? { nudged } : {}),
    },
    replay: { events: replay, interrupted },
    evidence: restoreEvidence(evidenceRows, committed),
    inForce,
  };
}

function withoutReasoning(messages: Message[]): Message[] {
  return messages.flatMap((message): Message[] => {
    if (message.role !== "assistant") return [message];
    const parts = message.parts.filter((part) => part.type !== "reasoning");
    return parts.length ? [{ role: "assistant", parts }] : [];
  });
}

/**
 * The main agent's streamed text kept as one event per stretch of text, written just before the next
 * event of any run. What the main agent thought is not kept, only that it thought and when (one empty
 * reasoning event per stretch of thinking, so a resumed turn shows how long it thought); sub-agents'
 * reasoning and text are not kept (their reports and messages are).
 */
export class TextCoalescer {
  private pending: EventEnvelope | undefined;

  add(envelope: EventEnvelope): EventEnvelope[] {
    const { event } = envelope;
    if (event.type === "model.reasoning.delta") {
      if (envelope.parent !== undefined || this.pending?.event.type === "model.reasoning.delta") return [];
      // Text streamed before it goes first; the thinking is marked from its first delta.
      const before = this.flush();
      this.pending = { ...envelope, event: { type: "model.reasoning.delta", text: "" } };
      return before;
    }
    if (event.type === "model.text.delta") {
      if (envelope.parent !== undefined) return [];
      // Thinking marked before it ends here.
      const before = this.pending?.event.type === "model.reasoning.delta" ? this.flush() : [];
      const text = this.pending?.event.type === "model.text.delta" ? this.pending.event.text : "";
      this.pending = {
        ...(this.pending ?? envelope),
        event: { type: "model.text.delta", text: text + event.text },
      };
      return before;
    }
    // Anything else may add to the transcript, so the text streamed before it goes first.
    return [...this.flush(), envelope];
  }

  flush(): EventEnvelope[] {
    const pending = this.pending;
    this.pending = undefined;
    return pending ? [pending] : [];
  }
}
