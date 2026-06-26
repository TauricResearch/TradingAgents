import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ResilientWs, buildRunUrl } from "../lib/ws";
import { useUi } from "../store/ui";

export type WsStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export function useRunStream(runId: string | null) {
  const appendEvent = useUi((s) => s.appendEvent);
  const qc = useQueryClient();
  const [status, setStatus] = useState<WsStatus>("idle");
  const lastIdRef = useRef<string | null>(null);
  const clientRef = useRef<ResilientWs | null>(null);

  useEffect(() => {
    if (runId == null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setStatus("idle");
      return;
    }
    // Reset cursor when runId changes so the new WS doesn't send a
    // stale `since` param from a different run.
    lastIdRef.current = null;
    // A fresh ResilientWs starts without a `since` cursor, so the
    // server replays every event for this runId. Wipe any pre-existing
    // buffer entries (typically from a REST replay) first so the
    // replay doesn't duplicate them. The buffer clear is deferred to
    // the first message handler to avoid losing events between the
    // clear call and the WS handshake completing.
    let bufferCleared = false;
    const client = new ResilientWs({
      url: () => buildRunUrl(runId, lastIdRef.current || undefined),
      onMessage: (evt) => {
        if (!bufferCleared) {
          bufferCleared = true;
          useUi.getState().clearEventBuffer(runId);
        }
        if (typeof evt.id === "string") lastIdRef.current = evt.id;
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
              state.setLastRunIdForTicker(ticker, runId);
              state.setRunStartedAtForTicker(ticker, null);
              // The run.json was updated with decision_action etc. on disk.
              // Invalidate the React Query cache so the ticker runs dropdown
              // and run list pick up the final action / target / confidence.
              qc.invalidateQueries({ queryKey: ["ticker-runs", ticker] });
              qc.invalidateQueries({ queryKey: ["runs", "list"] });
              // Also invalidate the run-detail cache so useRestoredRunEvents
              // fetches the completed run's events instead of stale "running"
              // data when the user switches back to this ticker.
              qc.invalidateQueries({ queryKey: ["run-detail", ticker] });
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
  }, [runId, appendEvent, qc]);

  return { status };
}
