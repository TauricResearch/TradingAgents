/**
 * F2 - React hook binding the run reducer to the live SSE stream.
 *
 * Lifecycle per run_id:
 *   mount / run_id change -> status "loading"
 *   getRun(run_id) resolves -> dispatch snapshot -> status "replaying"
 *   openRunStream(run_id, 0, ...) -> live events fold into reducer
 *   terminal event or stream close -> if terminal, status "closed"; else
 *     reconnect after a short backoff to recover any events the broker live
 *     queue missed (resilience against fast runs / transport drops).
 *   run_id === null -> status "idle", state reset.
 */
import { useEffect, useReducer, useRef, useState } from "react";
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
}

const TERMINAL_RUN_STATUSES = new Set(["completed", "failed", "cancelled", "interrupted"]);
const RECONNECT_DELAY_MS = 800;
const MAX_RECONNECTS = 20;

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
  const closedRef = useRef(false);
  const lastSeqRef = useRef(0);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

    const id: string = run_id;
    closedRef.current = false;
    let cancelled = false;
    setStatus("loading");
    setError(null);

    const streamFrom = (after: number): void => {
      if (cancelled || closedRef.current) return;
      const subscription = openRunStream(id, after, {
        onEvent: (event: PersistedEventDTO) => {
          if (cancelled || closedRef.current) return;
          lastSeqRef.current = Math.max(lastSeqRef.current, event.sequence);
          dispatch({ type: "event", event });
          setStatus("live");
        },
        onClose: () => {
          if (cancelled || closedRef.current) return;
          // The stream closed. Re-fetch the snapshot to decide: if the run
          // is terminal AND we have already seen its last event, we are done.
          // Otherwise reconnect from the last seen sequence to drain any
          // events the broker live queue missed (fast-worker resilience).
          if (reconnectCountRef.current >= MAX_RECONNECTS) {
            setStatus("error");
            setError(new Error("SSE reconnected too many times without reaching a terminal state"));
            return;
          }
          reconnectCountRef.current += 1;
          reconnectTimerRef.current = setTimeout(() => {
            if (cancelled || closedRef.current) return;
            getRun(id)
              .then((snap: RunSnapshotDTO) => {
                if (cancelled || closedRef.current) return;
                // Do NOT dispatch({type:"snapshot"}) here. The snapshot action
                // returns createInitialState(snapshot) -- only meta+roles --
                // which would wipe the turns/timeline/tool_calls already
                // replayed into state (Bug 1: viewing a completed history run
                // made the timeline vanish ~800ms after SSE replay finished).
                // Reconnect only needs to know whether the run reached a
                // terminal status with all events seen; otherwise re-subscribe
                // from the last seen sequence and let live/replayed events
                // update state normally.
                if (
                  TERMINAL_RUN_STATUSES.has(snap.status) &&
                  snap.latest_sequence <= lastSeqRef.current
                ) {
                  // Terminal and we have seen every event.
                  setStatus("closed");
                  return;
                }
                // Either still running, or terminal but we missed events:
                // re-subscribe from the last seen sequence.
                streamFrom(lastSeqRef.current);
              })
              .catch((err: unknown) => {
                if (cancelled || closedRef.current) return;
                setError(err instanceof Error ? err : new Error(String(err)));
                setStatus("error");
              });
          }, RECONNECT_DELAY_MS);
        },
        onError: (err: Error) => {
          if (cancelled || closedRef.current) return;
          setError(err);
          setStatus("error");
        },
      });
      if (cancelled || closedRef.current) {
        subscription.close();
        return;
      }
      subscriptionRef.current = subscription;
    };

    getRun(id)
      .then((snapshot: RunSnapshotDTO) => {
        if (cancelled || closedRef.current) return;
        lastSeqRef.current = 0;
        reconnectCountRef.current = 0;
        dispatch({ type: "snapshot", snapshot });
        setStatus("replaying");
        streamFrom(0);
      })
      .catch((err: unknown) => {
        if (cancelled || closedRef.current) return;
        setError(err instanceof Error ? err : new Error(String(err)));
        setStatus("error");
      });

    return () => {
      cancelled = true;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const sub = subscriptionRef.current;
      if (sub) {
        sub.close();
        subscriptionRef.current = null;
      }
    };
  }, [run_id]);

  return { state, status, error };
}