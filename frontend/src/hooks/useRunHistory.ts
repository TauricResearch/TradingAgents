/**
 * F3 - Hook for loading the run history list from GET /api/runs.
 *
 * Fetches once on mount; exposes refresh() so the layout can re-fetch after a
 * run starts/ends (e.g. after createRun resolves or a terminal stream event
 * arrives). The backend returns runs newest-first; this hook preserves that
 * order without client-side sorting or dedup.
 */
import { useCallback, useEffect, useState } from "react";
import type { RunSummaryDTO } from "../api/contracts";
import { listRuns } from "../api/client";

export interface UseRunHistoryResult {
  runs: RunSummaryDTO[];
  loading: boolean;
  error: Error | null;
  refresh: () => Promise<void>;
}

export function useRunHistory(): UseRunHistoryResult {
  const [runs, setRuns] = useState<RunSummaryDTO[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);

  const refresh = useCallback((): Promise<void> => {
    setLoading(true);
    setError(null);
    return listRuns()
      .then((result: RunSummaryDTO[]) => {
        setRuns(result);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err : new Error(String(err)));
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { runs, loading, error, refresh };
}
