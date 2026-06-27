import { useMemo } from "react";
import { useUi } from "../store/ui";
import type { WsEvent } from "../lib/events";

export function useFocusedRunEvents(): WsEvent[] {
  const focused = useUi((s) => s.focusedTicker);
  // Active (streaming) run takes priority so the user sees live events.
  // Historical (user-picked) run is next so the user can keep viewing
  // an older run. Falls back to the last completed run id.
  const runId = useUi((s) => {
    if (focused == null) return null;
    const active = s.activeRunIdByTicker[focused];
    if (active != null) return active;
    const historical = s.historicalRunIdByTicker[focused];
    if (historical != null) return historical;
    return s.lastRunIdByTicker[focused] ?? null;
  });
  const events = useUi((s) => s.eventBuffer);
  return useMemo(() => {
    if (focused == null || runId == null) return [];
    return events.filter((e) => e.run_id === runId);
  }, [focused, runId, events]);
}
