import { useEffect, useMemo, useRef } from "react";
import { useUi } from "../store/ui";
import type { WsEvent } from "../lib/events";

export function useFocusedRunEvents(): WsEvent[] {
  const focused = useUi((s) => s.focusedTicker);
  // Historical (user-picked) run takes priority so the user can keep
  // viewing an older run while a new one streams in. If the user
  // hasn't picked one, fall back to the latest run id for the ticker.
  const runId = useUi((s) => {
    if (focused == null) return null;
    const historical = s.historicalRunIdByTicker[focused];
    if (historical != null) return historical;
    return s.lastRunIdByTicker[focused] ?? null;
  });
  // Clear any stale buffered events for this runId when the run we're
  // focusing on CHANGES (REST-replay → live-WS handoff: the next live
  // WS will replay the same events, so wipe the duplicates first).
  // Skip the initial mount so test setups and first-paint hydration
  // can pre-populate the buffer without being wiped.
  const firstRenderRef = useRef(true);
  useEffect(() => {
    if (firstRenderRef.current) {
      firstRenderRef.current = false;
      return;
    }
    if (!runId) return;
    useUi.getState().clearEventBuffer(runId);
  }, [runId]);
  const events = useUi((s) => s.eventBuffer);
  return useMemo(() => {
    if (focused == null || runId == null) return [];
    return events.filter((e) => e.run_id === runId);
  }, [focused, runId, events]);
}
