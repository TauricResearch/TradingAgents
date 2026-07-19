/**
 * F2 - SSE consumer for a single TradingAgents run event stream.
 *
 * Uses the browser EventSource API. EventSource auto-reconnects on transport
 * errors and resends the Last-Event-ID header; the backend (api.py
 * stream_events / _event_cursor) honors Last-Event-ID and the `after` query
 * cursor. We only pass `after` on the initial open; on reconnect EventSource
 * supplies Last-Event-ID automatically and the two must agree (the backend
 * rejects mismatches with event_cursor_mismatch, which surfaces as onError).
 *
 * SSE wire format emitted by the backend (api.py event_stream):
 *   id: {sequence}\n
 *   event: {type}\n
 *   data: {json envelope}\n\n
 * Keepalive comments are emitted as `: {comment}\n\n`.
 */
import type { PersistedEventDTO } from "./contracts";
import { API, TERMINAL_STREAM_EVENTS } from "./contracts";
import { API_BASE } from "./client";

const SAFE_RUN_ID = /^[A-Za-z0-9_-]+$/;

export interface SseHandlers {
  /** Called for each persisted event reconstructed from the SSE data frame. */
  onEvent(event: PersistedEventDTO): void;
  /**
   * Keepalive comment handler. NOTE: the browser EventSource API consumes
   * `: comment` lines internally and never surfaces them to JavaScript, so
   * this is never invoked with the standard EventSource transport. It exists
   * for interface completeness / future fetch-based SSE readers.
   */
  onKeepalive?(comment: string): void;
  /**
   * Called when EventSource fires `error` (transport disconnect). The browser
   * auto-reconnects; the stream is NOT closed unless a terminal event arrives.
   */
  onError?(error: Error): void;
  /** Called once when the stream closes (terminal event or explicit close). */
  onClose?(): void;
}

export interface SseSubscription {
  close(): void;
}

/**
 * Open a live event stream for a run, starting after `after` (the snapshot's
 * latest_sequence). Returns a handle whose close() tears down the EventSource.
 *
 * EventSource has no wildcard listener, so to receive every named event in a
 * single code path we shadow dispatchEvent on the instance and inspect each
 * dispatched MessageEvent. `open`/`error` are plain Events (not MessageEvents)
 * and pass through to the onopen/onerror IDL handlers unchanged.
 */
export function openRunStream(
  run_id: string,
  after: number,
  handlers: SseHandlers,
): SseSubscription {
  if (!SAFE_RUN_ID.test(run_id)) {
    throw new RangeError(`Refusing to interpolate invalid run_id: ${run_id}`);
  }
  const url = `${API_BASE}${API.events(run_id, after)}`;
  const source = new EventSource(url);
  let closed = false;

  const close = (): void => {
    if (closed) return;
    closed = true;
    try {
      source.close();
    } catch {
      // EventSource.close should not throw; guard defensively.
    }
  };

  const handleEvent = (sseType: string, rawData: unknown): void => {
    if (closed) return;
    if (typeof rawData !== "string" || rawData.length === 0) {
      handlers.onError?.(new Error("SSE event data is empty or non-string"));
      return;
    }
    let parsed: PersistedEventDTO;
    try {
      parsed = JSON.parse(rawData) as PersistedEventDTO;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      handlers.onError?.(new Error(`SSE JSON parse failed: ${msg}`));
      return;
    }
    // The SSE `event:` field is authoritative for the type. Assert it matches
    // payload.type; if they disagree, the wire is corrupt - report and skip.
    // (For unnamed `message` frames sseType is "" and we skip the assertion,
    // letting payload.type drive dispatch defensively.)
    if (sseType !== "" && parsed.type !== sseType) {
      handlers.onError?.(
        new Error(
          `SSE type mismatch: event field="${sseType}" payload.type="${parsed.type}"`,
        ),
      );
      return;
    }
    handlers.onEvent(parsed);
    if (TERMINAL_STREAM_EVENTS.some((t) => t === parsed.type)) {
      handlers.onClose?.();
      close();
    }
  };

  source.onopen = (): void => {
    // No-op per spec; the consumer flips to "live" on the first event.
  };

  source.onerror = (): void => {
    if (closed) return;
    // EventSource fires `error` on disconnect; the browser auto-reconnects.
    // Do NOT close here - only terminal events close the stream.
    handlers.onError?.(
      new Error("SSE connection error; browser will auto-reconnect"),
    );
  };

  // Capture the original prototype method before shadowing it.
  const originalDispatch = source.dispatchEvent.bind(source);
  source.dispatchEvent = (event: Event): boolean => {
    if (event instanceof MessageEvent) {
      if (event.type === "message") {
        // Unnamed data frame; backend always sends named events, but handle
        // defensively by letting payload.type drive dispatch.
        handleEvent("", event.data);
      } else if (event.type !== "open" && event.type !== "error") {
        handleEvent(event.type, event.data);
      }
    }
    return originalDispatch(event);
  };

  return { close };
}
