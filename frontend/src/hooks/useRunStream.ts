/**
 * F2 - React hook binding the run reducer to the live SSE stream.
 *
 * Lifecycle per run_id:
 *   mount / run_id change -> status "loading"
 *   getRun(run_id) resolves -> dispatch seed(createInitialState(snapshot))
 *                              -> status "replaying"
 *   openRunStream(run_id, snapshot.latest_sequence, ...)
 *   first event with sequence > snapshot.latest_sequence -> status "live"
 *   terminal event or stream close -> status "closed"
 *   fetch / stream error -> status "error"
 *   run_id === null -> status "idle", state null
 *
 * Sequence dedup is handled inside runReducer (per task statement); this hook
 * does not perform its own dedup. Cleanup on unmount or run_id change closes
 * the subscription and invalidates in-flight fetches.
 *
 * Assumed ./reducer module exports (sibling F2 deliverable):
 *   export function createInitialState(snapshot: RunSnapshotDTO): ReducerState;
 *   export function runReducer(
 *     state: ReducerState | null,
 *     action: { type: "seed"; state: ReducerState | null }
 *            | { type: "event"; event: PersistedEventDTO },
 *   ): ReducerState | null;
 * The reducer must accept `ReducerState | null` so useReducer can be seeded
 * with null before the snapshot arrives.
 */
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type { ReducerState } from "../state/model";
import type { PersistedEventDTO, RunSnapshotDTO } from "../api/contracts";
import { getRun } from "../api/client";
import { openRunStream } from "../api/eventSource";
import type { SseSubscription } from "../api/eventSource";
import { createInitialState, runReducer } from "../state/runReducer";
import type { ReducerAction } from "../state/runReducer";

export type RunStreamStatus =
  | "idle"
  | "loading"
  | "live"
  | "replaying"
  | "closed"
  | "error";

export interface UseRunStreamResult {
  state: ReducerState | null;
  status: RunStreamStatus;
  error: Error | null;
  close: () => void;
}

export function useRunStream(run_id: string | null): UseRunStreamResult {
  const [state, dispatch] = useReducer(
    runReducer as (s: ReducerState, a: ReducerAction) => ReducerState,
    createInitialState(),
  );
  const [status, setStatus] = useState<RunStreamStatus>(
    run_id === null ? "idle" : "loading",
  );
  const [error, setError] = useState<Error | null>(null);
  const subscriptionRef = useRef<SseSubscription | null>(null);
  /** Guards manual close() against late-arriving callbacks / in-flight fetch. */
  const closedRef = useRef(false);
  /** Mirrors run_id during render so close() can no-op when idle. */
  const runIdRef = useRef<string | null>(run_id);
  runIdRef.current = run_id;

  const close = useCallback((): void => {
    // No-op when there is no active run; preserves the "idle" contract.
    if (runIdRef.current === null) return;
    closedRef.current = true;
    const sub = subscriptionRef.current;
    if (sub) {
      sub.close();
      subscriptionRef.current = null;
    }
    setStatus("closed");
  }, []);

  useEffect(() => {
    if (run_id === null) {
      closedRef.current = false;
      const sub = subscriptionRef.current;
      if (sub) {
        sub.close();
        subscriptionRef.current = null;
      }
      dispatch({ type: "reset" });
      setStatus("idle");
      setError(null);
      return;
    }

    // Capture as const so the narrowing (string, not string | null) is
    // preserved inside the async .then closure below.
    const id: string = run_id;
    closedRef.current = false;
    let cancelled = false;
    setStatus("loading");
    setError(null);

    getRun(id)
      .then((snapshot: RunSnapshotDTO) => {
        if (cancelled || closedRef.current) return;
        dispatch({ type: "snapshot", snapshot });
        setStatus("replaying");
        const subscription = openRunStream(id, snapshot.latest_sequence, {
          onEvent: (event: PersistedEventDTO) => {
            if (cancelled || closedRef.current) return;
            dispatch({ type: "event", event });
            if (event.sequence > snapshot.latest_sequence) {
              setStatus("live");
            }
          },
          onClose: () => {
            if (cancelled || closedRef.current) return;
            setStatus("closed");
          },
          onError: (err: Error) => {
            if (cancelled || closedRef.current) return;
            setError(err);
            setStatus("error");
          },
        });
        // If close() or unmount raced with stream open, tear it down immediately.
        if (cancelled || closedRef.current) {
          subscription.close();
          return;
        }
        subscriptionRef.current = subscription;
      })
      .catch((err: unknown) => {
        if (cancelled || closedRef.current) return;
        setError(err instanceof Error ? err : new Error(String(err)));
        setStatus("error");
      });

    return () => {
      cancelled = true;
      const sub = subscriptionRef.current;
      if (sub) {
        sub.close();
        subscriptionRef.current = null;
      }
    };
  }, [run_id]);

  return { state, status, error, close };
}
