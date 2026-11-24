// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The results a session's tools returned, recorded under ids (`e1`, `e2`, ...) the model cites and
 * references. One store per session publishes for every run of it, the main agent's and its
 * sub-agents': ids are unique across runs, each record names its run and step, a cancelled call or a
 * turn already closed publishes nothing, and only results that fit their tool's contract reach it.
 *
 * Records are written to the session as they are published, before the turn's commit, so a sync
 * carries them with the turn; on resume only the records of committed turns come back. A payload syncs
 * only when its data may be copied with a synced session (Tauric's own, or computed from such alone)
 * and it fits the caps; otherwise it is kept on this computer beside the session (`keep`), and the
 * record and its preview are written as usual.
 */
import { citedIds, type JsonValue, type Source } from "../contracts/index.js";
import { EVIDENCE } from "../contracts/limits.js";
import type { ReferenceSource } from "./references.js";
import type { Provenance } from "./tool.js";

export type EvidenceRecord = {
  id: string;
  turn: string;
  run: string;
  /** The run's step that made the call. */
  step: number;
  call: string;
  tool: string;
  args: JsonValue;
  /** The call's arguments in a few words, as people see them. */
  label: string;
  /** The data; absent when it was kept on the computer that fetched it and this is another. */
  payload?: unknown;
  /** The start of the rendered result, kept with the record wherever it goes. */
  preview: string;
  /** The records the call's arguments referenced. */
  inputs: string[];
  provenance: Provenance;
  /** The payload's size as JSON. */
  bytes: number;
  /** The payload is kept on this computer, not written to the session; the record and preview are. */
  local_only?: true;
};

export type EvidenceDraft = Pick<
  EvidenceRecord,
  "call" | "tool" | "args" | "label" | "preview" | "inputs" | "provenance"
> & {
  payload: unknown;
};

/** One call's view of the store: what it may reference, and where its own result is recorded. */
export type EvidenceScope = ReferenceSource & {
  readonly run: string;
  readonly step: number;
  get(id: string): EvidenceRecord | undefined;
  /** Record a result; undefined when the call was cancelled or its turn has closed. */
  publish(draft: EvidenceDraft): EvidenceRecord | undefined;
};

export type RestoredEvidence = { records: EvidenceRecord[]; next: number };

type MetaRow = Omit<EvidenceRecord, "payload"> & { kind: "evidence"; payload?: unknown; parts?: number };
type PartRow = { kind: "evidence.part"; id: string; i: number; data: string };
export type EvidenceRow = MetaRow | PartRow;

export class EvidenceStore {
  private readonly records = new Map<string, EvidenceRecord>();
  private next: number;
  /** Payload bytes written to the session so far. */
  private written = 0;
  private readonly closed = new Set<string>();

  /**
   * `sink`: where records are written as rows (the session's file); `keep`: where a payload that stays on
   * this computer is kept, before its record's rows are written; `restored`: what a resume reads back.
   */
  constructor(
    private readonly sink?: (rows: EvidenceRow[]) => void,
    restored?: RestoredEvidence,
    private readonly keep?: (id: string, payload: unknown) => void,
  ) {
    this.next = restored?.next ?? 1;
    for (const record of restored?.records ?? []) {
      this.records.set(record.id, record);
      if (!record.local_only) this.written += record.bytes;
    }
  }

  get(id: string): EvidenceRecord | undefined {
    return this.records.get(id);
  }

  /** The records a turn published, in order. */
  of(turn: string): EvidenceRecord[] {
    return [...this.records.values()].filter((record) => record.turn === turn);
  }

  /** Publish nothing more for `turn`: its outcome is being written. */
  closeTurn(turn: string): void {
    this.closed.add(turn);
  }

  /** Whether a result's data may be copied with a synced session: its own, and every record it was computed from. */
  private syncs(draft: EvidenceDraft): boolean {
    return (
      draft.provenance.syncs === true &&
      draft.inputs.every((id) => {
        const input = this.records.get(id);
        return input !== undefined && !input.local_only;
      })
    );
  }

  /** The view of one step's calls in run `run` of `turn`; a call publishes only while `signal` is live. */
  scope(turn: string, run: string, step: number, signal: AbortSignal): EvidenceScope {
    const first = this.next;
    return {
      run,
      step,
      // Ids from here on are published during the step: the step's calls, or other runs' at the same time.
      pending: (id) => !this.records.has(id) && Number(id.slice(1)) >= first,
      get: (id) => this.records.get(id),
      payload: (id) => {
        const record = this.records.get(id);
        if (!record) return undefined;
        const at = { run: record.run, step: record.step };
        return record.payload === undefined
          ? { localOnly: true as const, ...at }
          : { payload: record.payload, ...at };
      },
      publish: (draft) => {
        if (signal.aborted || this.closed.has(turn)) return undefined;
        const bytes = Buffer.byteLength(JSON.stringify(draft.payload) ?? "null");
        const kept =
          !this.syncs(draft) || bytes > EVIDENCE.recordBytes || this.written + bytes > EVIDENCE.sessionBytes;
        const record: EvidenceRecord = {
          id: `e${this.next++}`,
          turn,
          run,
          step,
          ...draft,
          bytes,
          ...(kept ? { local_only: true as const } : {}),
        };
        this.records.set(record.id, record);
        if (kept) this.keep?.(record.id, record.payload);
        else this.written += bytes;
        this.sink?.(evidenceRows(record));
        return record;
      },
    };
  }
}

/** The records an answer cites, numbered by first appearance, and the ids it cites that name none. */
export function citationsOf(
  answer: string,
  get: (id: string) => EvidenceRecord | undefined,
): { sources: Source[]; missing: string[] } {
  const sources: Source[] = [];
  const missing: string[] = [];
  for (const id of citedIds(answer, (id) => get(id) !== undefined)) {
    const record = get(id);
    if (!record) {
      missing.push(id);
      continue;
    }
    const { source, subject, as_of } = record.provenance;
    sources.push({
      n: sources.length + 1,
      id,
      tool: record.tool,
      label: record.label,
      ...(subject ? { subject } : {}),
      source,
      ...(as_of ? { asOf: as_of } : {}),
    });
  }
  return { sources, missing };
}

/** A record as session rows: one, with its payload, when it fits a line; else its payload split across lines. */
function evidenceRows(record: EvidenceRecord): EvidenceRow[] {
  const { payload, ...meta } = record;
  if (record.local_only) return [{ kind: "evidence", ...meta }];
  const whole: MetaRow = { kind: "evidence", ...meta, payload };
  if (lineBytes(whole) <= EVIDENCE.lineBytes) return [whole];
  const text = JSON.stringify(payload);
  const parts: PartRow[] = [];
  for (let at = 0; at < text.length; ) {
    let size = Math.min(text.length - at, EVIDENCE.lineBytes);
    let part: PartRow;
    for (;;) {
      part = { kind: "evidence.part", id: record.id, i: parts.length, data: text.slice(at, at + size) };
      const bytes = lineBytes(part);
      if (bytes <= EVIDENCE.lineBytes) break;
      // Escaping makes the line longer than its characters: aim below the limit by what it overshot.
      size = Math.max(1, Math.floor(size * (EVIDENCE.lineBytes / bytes) * 0.98));
    }
    parts.push(part);
    at += size;
  }
  return [{ kind: "evidence", ...meta, parts: parts.length }, ...parts];
}

/**
 * The records of `committed` turns among a session's rows, and the next id: past every id written,
 * including those of a turn that never committed, so an id is never given twice.
 */
export function restoreEvidence(
  rows: readonly EvidenceRow[],
  committed: ReadonlySet<string>,
): RestoredEvidence {
  let next = 1;
  const metas: MetaRow[] = [];
  const parts = new Map<string, string[]>();
  for (const row of rows) {
    if (row.kind === "evidence") {
      next = Math.max(next, Number(row.id.slice(1)) + 1);
      if (committed.has(row.turn)) metas.push(row);
    } else {
      const list = parts.get(row.id) ?? [];
      list[row.i] = row.data;
      parts.set(row.id, list);
    }
  }
  const records: EvidenceRecord[] = [];
  for (const { kind: _, parts: count, payload, ...record } of metas) {
    if (count === undefined) {
      records.push(record.local_only ? record : { ...record, payload });
      continue;
    }
    const list = parts.get(record.id) ?? [];
    // A record whose lines did not all reach the file is left out rather than read wrong.
    if (list.length !== count || list.some((data) => data === undefined)) continue;
    records.push({ ...record, payload: JSON.parse(list.join("")) });
  }
  return { records, next };
}

function lineBytes(row: EvidenceRow): number {
  return Buffer.byteLength(JSON.stringify(row)) + 1;
}
