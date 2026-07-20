/**
 * F2 - SSE consumer for a single TradingAgents run event stream.
 *
 * Uses fetch + ReadableStream reader (not EventSource) so we can parse every
 * named event frame in one code path. EventSource requires per-type
 * addEventListener for named events and has no wildcard, which is brittle
 * across 30+ event types; fetch streaming lets us parse the SSE wire format
 * directly.
 *
 * SSE wire format (api.py event_stream):
 *   id: {sequence}\n
 *   event: {type}\n
 *   data: {json envelope}\n\n
 * Keepalive comments: `: {comment}\n\n` (ignored).
 */
import type { PersistedEventDTO } from "./contracts";
import { API, TERMINAL_STREAM_EVENTS } from "./contracts";
import { API_BASE } from "./client";

const SAFE_RUN_ID = /^[A-Za-z0-9_-]+$/;

export interface SseHandlers {
  onEvent(event: PersistedEventDTO): void;
  onKeepalive?(comment: string): void;
  onError?(error: Error): void;
  onClose?(): void;
}

export interface SseSubscription {
  close(): void;
}

export function openRunStream(
  run_id: string,
  after: number,
  handlers: SseHandlers,
): SseSubscription {
  if (!SAFE_RUN_ID.test(run_id)) {
    throw new RangeError(`Refusing to interpolate invalid run_id: ${run_id}`);
  }
  const url = `${API_BASE}${API.events(run_id, after)}`;
  const controller = new AbortController();
  let closed = false;

  const close = (): void => {
    if (closed) return;
    closed = true;
    controller.abort();
  };

  // Drive the fetch + parse loop in an async IIFE. The subscription handle
  // only needs close(); the loop self-terminates on terminal event, stream
  // end, abort, or error.
  void (async (): Promise<void> => {
    try {
      const resp = await fetch(url, {
        method: "GET",
        headers: { Accept: "text/event-stream" },
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) {
        if (!closed) handlers.onError?.(new Error(`SSE HTTP ${resp.status}`));
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let frameEvent = "";
      let frameData = "";

      const flushFrame = (): void => {
        if (frameData === "") {
          frameEvent = "";
          return;
        }
        let parsed: PersistedEventDTO;
        try {
          parsed = JSON.parse(frameData) as PersistedEventDTO;
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          handlers.onError?.(new Error(`SSE JSON parse failed: ${msg}`));
          frameEvent = "";
          frameData = "";
          return;
        }
        if (frameEvent !== "" && parsed.type !== frameEvent) {
          handlers.onError?.(
            new Error(
              `SSE type mismatch: event="${frameEvent}" payload.type="${parsed.type}"`,
            ),
          );
          frameEvent = "";
          frameData = "";
          return;
        }
        handlers.onEvent(parsed);
        const isTerminal = TERMINAL_STREAM_EVENTS.some((t) => t === parsed.type);
        frameEvent = "";
        frameData = "";
        if (isTerminal) {
          handlers.onClose?.();
          close();
        }
      };

      while (!closed) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        buffer = buffer.replace(/\r\n/g, "\n");
        let sep: number;
        while ((sep = buffer.indexOf("\n\n")) >= 0) {
          const rawFrame = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          if (rawFrame === "") continue;
          for (const line of rawFrame.split("\n")) {
            if (line.startsWith(":")) {
              handlers.onKeepalive?.(line.slice(1).trim());
              continue;
            }
            if (line.startsWith("event:")) {
              frameEvent = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              frameData += line.slice(5).trim();
            }
            // id: line ignored; sequence lives in parsed.sequence.
          }
          flushFrame();
          if (closed) break;
        }
      }
      if (!closed) {
        // Server closed the stream without a terminal event.
        handlers.onClose?.();
      }
    } catch (err) {
      if (closed || controller.signal.aborted) return;
      const msg = err instanceof Error ? err.message : String(err);
      handlers.onError?.(new Error(`SSE stream error: ${msg}`));
    }
  })();

  return { close };
}