/**
 * F2 - Thin React context providing per-run state isolation for the
 * TradingAgents workbench. Holds the currently selected run_id and the live
 * stream handle from useRunStream; F3 components consume via useWorkbenchStore.
 *
 * Minimal: no UI, no selectors, no memoization beyond a stable selectRun.
 * The context value is recreated when run_id or stream changes, which is the
 * desired re-render trigger.
 */
import { createContext, useCallback, useContext, useState } from "react";
import type { ReactNode } from "react";
import { useRunStream } from "../hooks/useRunStream";

export interface WorkbenchStoreValue {
  run_id: string | null;
  selectRun: (id: string | null) => void;
  stream: ReturnType<typeof useRunStream>;
}

const WorkbenchContext = createContext<WorkbenchStoreValue | null>(null);

export function WorkbenchProvider({
  children,
}: {
  children: ReactNode;
}): JSX.Element {
  const [run_id, setRunId] = useState<string | null>(null);
  const stream = useRunStream(run_id);
  const selectRun = useCallback((id: string | null): void => {
    setRunId(id);
  }, []);
  const value: WorkbenchStoreValue = { run_id, selectRun, stream };
  return (
    <WorkbenchContext.Provider value={value}>
      {children}
    </WorkbenchContext.Provider>
  );
}

export function useWorkbenchStore(): WorkbenchStoreValue {
  const ctx = useContext(WorkbenchContext);
  if (ctx === null) {
    throw new Error("useWorkbenchStore must be used within a WorkbenchProvider");
  }
  return ctx;
}
