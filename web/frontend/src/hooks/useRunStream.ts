import { useEffect, useRef, useState } from "react";
import { ResilientWs, buildRunUrl } from "../lib/ws";
import { useUi } from "../store/ui";

export type WsStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export function useRunStream(runId: number | null) {
  const appendEvent = useUi((s) => s.appendEvent);
  const [status, setStatus] = useState<WsStatus>("idle");
  const lastIdRef = useRef<number>(0);
  const clientRef = useRef<ResilientWs | null>(null);

  useEffect(() => {
    if (runId == null) {
      setStatus("idle");
      return;
    }
    const client = new ResilientWs({
      url: () => buildRunUrl(runId, lastIdRef.current || undefined),
      onMessage: (evt) => {
        if (typeof evt.id === "number") lastIdRef.current = Math.max(lastIdRef.current, evt.id);
        appendEvent(evt);
        // Terminal events clear the active-run marker for whatever ticker
        // was running this id, so the UI stops showing "running" once the
        // server has actually finished or failed. The store is keyed by
        // ticker, so we reverse-lookup the runId → ticker here.
        if (evt.type === "run_finished" || evt.type === "run_failed") {
          const state = useUi.getState();
          for (const [ticker, activeId] of Object.entries(state.activeRunIdByTicker)) {
            if (activeId === runId) {
              state.clearActiveRunForTicker(ticker);
              break;
            }
          }
        }
      },
      onStatus: setStatus,
    });
    clientRef.current = client;
    client.start();
    return () => {
      client.stop();
      clientRef.current = null;
    };
  }, [runId, appendEvent]);

  return { status };
}
