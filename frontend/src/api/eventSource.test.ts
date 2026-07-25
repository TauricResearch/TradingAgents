/**
 * eventSource SSE wire-format parsing tests (F104-F108).
 *
 * openRunStream uses fetch + ReadableStream (not EventSource) so it can parse
 * every named event frame in one code path. These tests mock fetch and feed
 * deterministic SSE byte chunks to verify: frame parsing, keepalive ignoring,
 * terminal-event close, and HTTP error reporting.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { openRunStream } from "./eventSource";
import type { PersistedEventDTO } from "./contracts";

function frame(seq: number, type: string, run_id: string): string {
  const data = JSON.stringify({
    event_id: `${run_id}:${seq}`,
    run_id,
    sequence: seq,
    timestamp: "2026-07-21T12:00:00Z",
    type,
    payload: { run_status: "running" },
    schema_version: 1,
  });
  return `id: ${seq}\nevent: ${type}\ndata: ${data}\n\n`;
}

function mockFetchChunks(chunks: string[], status = 200): void {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, body }),
  );
}

describe("eventSource SSE wire parsing", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("parses id/event/data frames into PersistedEventDTO (F104)", async () => {
    const events: PersistedEventDTO[] = [];
    mockFetchChunks([
      frame(1, "run.started", "run1"),
      frame(2, "role.status_changed", "run1"),
    ]);
    const sub = openRunStream("run1", 0, {
      onEvent: (e) => events.push(e),
      onClose: () => {},
      onError: () => {},
    });
    await vi.waitFor(() => expect(events).toHaveLength(2));
    expect(events[0].sequence).toBe(1);
    expect(events[0].type).toBe("run.started");
    expect(events[0].run_id).toBe("run1");
    expect(events[1].type).toBe("role.status_changed");
    sub.close();
  });

  it("ignores keepalive comment lines (F104)", async () => {
    const events: PersistedEventDTO[] = [];
    mockFetchChunks([": keepalive\n\n", frame(1, "run.started", "run1")]);
    openRunStream("run1", 0, {
      onEvent: (e) => events.push(e),
      onClose: () => {},
      onError: () => {},
    });
    await vi.waitFor(() => expect(events).toHaveLength(1));
  });

  it("handles split frames across chunks (partial frame reassembly)", async () => {
    const events: PersistedEventDTO[] = [];
    const full = frame(1, "run.started", "run1");
    const mid = Math.floor(full.length / 2);
    mockFetchChunks([full.slice(0, mid), full.slice(mid)]);
    const sub = openRunStream("run1", 0, {
      onEvent: (e) => events.push(e),
      onClose: () => {},
      onError: () => {},
    });
    await vi.waitFor(() => expect(events).toHaveLength(1));
    sub.close();
  });

  it("calls onClose when a terminal event arrives (F105)", async () => {
    let closed = false;
    mockFetchChunks([frame(1, "run.completed", "run1")]);
    const sub = openRunStream("run1", 0, {
      onEvent: () => {},
      onClose: () => {
        closed = true;
      },
      onError: () => {},
    });
    await vi.waitFor(() => expect(closed).toBe(true));
    sub.close();
  });

  it("reports non-2xx HTTP as onError", async () => {
    const onError = vi.fn();
    mockFetchChunks([], 500);
    openRunStream("run1", 0, {
      onEvent: () => {},
      onClose: () => {},
      onError,
    });
    await vi.waitFor(() => expect(onError).toHaveBeenCalled());
    expect(onError.mock.calls[0][0].message).toContain("500");
  });

  it("rejects invalid run_id before fetching", () => {
    expect(() =>
      openRunStream("bad run id!", 0, {
        onEvent: () => {},
        onClose: () => {},
        onError: () => {},
      }),
    ).toThrow(RangeError);
  });
});
