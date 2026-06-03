import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useUi } from "../store/ui";
import { fetchRunDetail, type RunDetail } from "../lib/api";

export function useRestoredRunEvents(focused: string | null): void {
  const lastRunId = useUi((s) => (focused ? s.lastRunIdByTicker[focused] ?? null : null));
  const restoreEvents = useUi((s) => s.restoreEvents);
  const clearLast = useUi((s) => s.clearLastRunIdForTicker);
  const lastFetchedRunIdRef = useRef<number | null>(null);

  const { data } = useQuery<RunDetail | null>({
    queryKey: ["run-detail", focused, lastRunId],
    queryFn: async () => {
      if (focused == null || lastRunId == null) return null;
      try {
        return await fetchRunDetail(lastRunId);
      } catch (e) {
        if (e instanceof Error && /404/.test(e.message)) {
          clearLast(focused);
          return null;
        }
        throw e;
      }
    },
    enabled: focused != null && lastRunId != null,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (!data || !focused) return;
    if (data.run.status === "running" || data.run.status === "queued") return;
    if (lastFetchedRunIdRef.current === data.run.id) return;
    lastFetchedRunIdRef.current = data.run.id;
    restoreEvents(data.run.id, data.events);
  }, [data, focused, restoreEvents]);
}
