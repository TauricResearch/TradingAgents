import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useUi } from "../store/ui";
import { fetchRunDetail, type RunDetail } from "../lib/api";

export function useRestoredRunEvents(focused: string | null): void {
  // Same source-of-truth as useFocusedRunEvents: the historical (user-picked)
  // run wins over the latest. Without this, picking an older run from the
  // history dropdown left the timeline empty (events filtered for the
  // historical id, but the hook only fetched the latest).
  const runId = useUi((s) => {
    if (focused == null) return null;
    const historical = s.historicalRunIdByTicker[focused];
    if (historical != null) return historical;
    return s.lastRunIdByTicker[focused] ?? null;
  });
  const restoreEvents = useUi((s) => s.restoreEvents);
  const clearLast = useUi((s) => s.clearLastRunIdForTicker);
  const clearHistorical = useUi((s) => s.clearHistoricalRunForTicker);
  const lastFetchedRunIdRef = useRef<string | null>(null);

  const { data } = useQuery<RunDetail | null>({
    queryKey: ["run-detail", focused, runId],
    queryFn: async () => {
      if (focused == null || runId == null) return null;
      try {
        return await fetchRunDetail(runId);
      } catch (e) {
        if (e instanceof Error && /404/.test(e.message)) {
          // The id we tried to load is gone from the DB. Whichever
          // pointer (historical or last) referenced it, clear it so the
          // UI stops trying to display the missing run.
          const s = useUi.getState();
          if (s.historicalRunIdByTicker[focused] === runId) {
            clearHistorical(focused);
          }
          if (s.lastRunIdByTicker[focused] === runId) {
            clearLast(focused);
          }
          return null;
        }
        throw e;
      }
    },
    enabled: focused != null && runId != null,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (!data || !focused) return;
    if (data.status === "running" || data.status === "queued") return;
    if (lastFetchedRunIdRef.current === data.id) return;
    lastFetchedRunIdRef.current = data.id;
    restoreEvents(data.id, data.events);
  }, [data, focused, restoreEvents]);
}
