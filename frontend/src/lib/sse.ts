/** SSE transport: one EventSource on /api/stream, named events map onto
 * the query cache. While healthy, polling relaxes to 60s.
 *
 * Two connection modes, decided by the server (/api/auth/config):
 * - same origin (default): EventSource("/api/stream"), cookie-authed,
 *   native auto-reconnect semantics preserved by our manual loop.
 * - direct (`stream_url` set): Firebase Hosting's proxy buffers responses
 *   and cannot carry SSE, so the EventSource connects straight to the
 *   Cloud Run origin, authenticated by a short-lived SINGLE-USE ticket
 *   minted through the normal session (GET /api/stream/ticket). Native
 *   EventSource reconnects would replay the consumed ticket and 401, so
 *   reconnection is manual: close, mint a fresh ticket, reconnect with
 *   the last seen event id.
 */
import type { QueryClient } from "@tanstack/react-query";

import { apiFetch, fetchAuthConfig } from "./api/client";
import { qk, setPollingInterval } from "./api/queries";
import { recordSuccess } from "./staleness";
import { usePipelineLiveStore } from "@/stores/pipelineLive";
import { useTickerStore } from "@/stores/ticker";
import { useUiStore } from "@/stores/ui";

export type StreamHealth = "connecting" | "open" | "down";

type HealthListener = (health: StreamHealth) => void;
const healthListeners = new Set<HealthListener>();
let health: StreamHealth = "connecting";

const RECONNECT_DELAY_MS = 4_000;

function setHealth(next: StreamHealth) {
  health = next;
  setPollingInterval(next === "open" ? 60_000 : 5_000);
  healthListeners.forEach((l) => l(next));
}

export function onStreamHealth(listener: HealthListener) {
  listener(health);
  healthListeners.add(listener);
  return () => healthListeners.delete(listener);
}

let streamBase: string | null | undefined; // undefined = not yet resolved

async function resolveStreamBase(): Promise<string | null> {
  if (streamBase !== undefined) return streamBase;
  try {
    const config = await fetchAuthConfig();
    streamBase = config.stream_url?.replace(/\/$/, "") ?? null;
  } catch {
    streamBase = null; // older backend: same-origin stream
  }
  return streamBase;
}

async function buildStreamUrl(lastEventId: string | null): Promise<string> {
  const base = await resolveStreamBase();
  const resume = lastEventId
    ? `last_event_id=${encodeURIComponent(lastEventId)}`
    : "";
  if (!base) return `/api/stream${resume ? `?${resume}` : ""}`;
  // apiFetch: session cookie + X-API-Key + the global 401 handler
  const { ticket } = await apiFetch<{ ticket: string }>("/api/stream/ticket");
  return `${base}/api/stream?ticket=${encodeURIComponent(ticket)}${
    resume ? `&${resume}` : ""
  }`;
}

export function startEventStream(client: QueryClient): () => void {
  let source: EventSource | null = null;
  let stopped = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let lastEventId: string | null = null;

  const bump = (event?: Event) => {
    const id = (event as MessageEvent | undefined)?.lastEventId;
    if (id) lastEventId = id;
    recordSuccess();
  };

  const scheduleReconnect = () => {
    if (stopped || reconnectTimer != null) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      void connect();
    }, RECONNECT_DELAY_MS);
  };

  const connect = async () => {
    if (stopped) return;
    let url: string;
    try {
      url = await buildStreamUrl(lastEventId);
    } catch {
      setHealth("down");
      scheduleReconnect();
      return;
    }
    if (stopped) return;

    source = new EventSource(url);

    source.onopen = () => {
      setHealth("open");
      bump();
    };

    source.onerror = () => {
      // manual reconnect everywhere: the direct path's ticket is single-use
      // (native retries would replay it and 401), and one code path beats
      // two. Cheap fixed delay; polling covers the gap.
      source?.close();
      source = null;
      setHealth("down");
      scheduleReconnect();
    };

    source.addEventListener("heartbeat", bump);

    source.addEventListener("run", (event) => {
      bump(event);
      useUiStore.getState().setPipelineProgress(null); // run finished
      usePipelineLiveStore.getState().clear();
      void client.invalidateQueries({ queryKey: qk.runs });
      void client.invalidateQueries({ queryKey: ["recommendation", "latest"] });
      void client.invalidateQueries({ queryKey: qk.regime });
      void client.invalidateQueries({ queryKey: qk.overview });
      void client.invalidateQueries({ queryKey: qk.journal });
      void client.invalidateQueries({ queryKey: qk.agents });
    });

    source.addEventListener("stage", (event) => {
      bump(event);
      try {
        const stage = JSON.parse((event as MessageEvent).data) as {
          stage: string;
          symbol?: string;
        };
        useUiStore.getState().setPipelineProgress({
          symbol: stage.symbol ?? "",
          stage: stage.stage,
        });
        usePipelineLiveStore.getState().push(stage.stage);
      } catch {
        /* malformed stage — ignore */
      }
    });

    source.addEventListener("alert", (event) => {
      bump(event);
      void client.invalidateQueries({ queryKey: qk.alerts });
      void client.invalidateQueries({ queryKey: qk.notifications });
    });

    source.addEventListener("position", (event) => {
      bump(event);
      void client.invalidateQueries({ queryKey: qk.status });
      void client.invalidateQueries({ queryKey: qk.journal });
    });

    source.addEventListener("status", (event) => {
      bump(event);
      try {
        client.setQueryData(qk.status, JSON.parse((event as MessageEvent).data));
      } catch {
        void client.invalidateQueries({ queryKey: qk.status });
      }
    });

    source.addEventListener("tick", (event) => {
      bump(event);
      try {
        const tick = JSON.parse((event as MessageEvent).data) as {
          symbol: string;
          last: number;
          bid?: number;
          ask?: number;
          source?: string;
        };
        useTickerStore.getState().setTick(tick.symbol, {
          last: tick.last,
          bid: tick.bid ?? null,
          ask: tick.ask ?? null,
          at: Date.now(),
          source: tick.source ?? "sse",
        });
      } catch {
        /* malformed tick — ignore */
      }
    });
  };

  void connect();

  return () => {
    stopped = true;
    if (reconnectTimer != null) clearTimeout(reconnectTimer);
    source?.close();
    setHealth("down");
  };
}
