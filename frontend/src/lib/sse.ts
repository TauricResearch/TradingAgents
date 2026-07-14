/** SSE transport: one EventSource on /api/stream (cookie-authed), named
 * events map onto the query cache. Native auto-reconnect + Last-Event-ID
 * resume; while healthy, polling relaxes to 60s. */
import type { QueryClient } from "@tanstack/react-query";

import { qk, setPollingInterval } from "./api/queries";
import { recordSuccess } from "./staleness";
import { useTickerStore } from "@/stores/ticker";
import { useUiStore } from "@/stores/ui";

export type StreamHealth = "connecting" | "open" | "down";

type HealthListener = (health: StreamHealth) => void;
const healthListeners = new Set<HealthListener>();
let health: StreamHealth = "connecting";

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

export function startEventStream(client: QueryClient): () => void {
  const source = new EventSource("/api/stream");

  const bump = () => recordSuccess();

  source.onopen = () => {
    setHealth("open");
    bump();
  };

  source.addEventListener("heartbeat", bump);
  source.onerror = () => setHealth("down"); // EventSource retries itself

  source.addEventListener("run", () => {
    bump();
    useUiStore.getState().setPipelineProgress(null); // run finished
    void client.invalidateQueries({ queryKey: qk.runs });
    void client.invalidateQueries({ queryKey: ["recommendation", "latest"] });
    void client.invalidateQueries({ queryKey: qk.regime });
    void client.invalidateQueries({ queryKey: qk.overview });
    void client.invalidateQueries({ queryKey: qk.journal });
    void client.invalidateQueries({ queryKey: qk.agents });
  });

  source.addEventListener("stage", (event) => {
    bump();
    try {
      const stage = JSON.parse((event as MessageEvent).data) as {
        stage: string;
        symbol?: string;
      };
      useUiStore.getState().setPipelineProgress({
        symbol: stage.symbol ?? "",
        stage: stage.stage,
      });
    } catch {
      /* malformed stage — ignore */
    }
  });

  source.addEventListener("alert", () => {
    bump();
    void client.invalidateQueries({ queryKey: qk.alerts });
    void client.invalidateQueries({ queryKey: qk.notifications });
  });

  source.addEventListener("position", () => {
    bump();
    void client.invalidateQueries({ queryKey: qk.status });
    void client.invalidateQueries({ queryKey: qk.journal });
  });

  source.addEventListener("status", (event) => {
    bump();
    try {
      client.setQueryData(qk.status, JSON.parse((event as MessageEvent).data));
    } catch {
      void client.invalidateQueries({ queryKey: qk.status });
    }
  });

  source.addEventListener("tick", (event) => {
    bump();
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

  return () => {
    source.close();
    setHealth("down");
  };
}
