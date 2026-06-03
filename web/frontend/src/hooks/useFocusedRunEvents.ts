import { useMemo } from "react";
import { useUi } from "../store/ui";
import type { WsEvent } from "../lib/events";

export function useFocusedRunEvents(): WsEvent[] {
  const focused = useUi((s) => s.focusedTicker);
  const runId = useUi((s) =>
    focused ? s.lastRunIdByTicker[focused] ?? null : null
  );
  const events = useUi((s) => s.eventBuffer);
  return useMemo(() => {
    if (focused == null || runId == null) return [];
    return events.filter((e) => e.run_id === runId);
  }, [focused, runId, events]);
}
