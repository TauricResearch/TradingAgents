/**
 * Fetches turn response artifacts without hiding long-run turns.
 *
 * The first window is loaded in full. Every later turn is also loaded, but is
 * initially presented as a bounded excerpt with an explicit expand action.
 * Requests are de-duplicated by run, turn, and load mode, and a small shared
 * queue keeps artifact reads below the browser's concurrent-request ceiling.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { Turn } from "../state/model";
import { readArtifactText } from "../api/client";
import { extractResponse } from "../domain/responseExtractor";

export interface LoadedResponse {
  text: string | null;
  badge: string | null;
  loading: boolean;
  error: string | null;
  /** True when the full text has been fetched; false if only an excerpt exists. */
  fullyLoaded: boolean;
}

interface UseTurnResponsesOptions {
  run_id: string | null;
  turns: Turn[];
  /** Number of turns to eagerly fetch in full from the start of the list. */
  eagerWindow?: number;
  /** Maximum characters to show in the excerpt of later turns. */
  excerptBudget?: number;
}

interface UseTurnResponsesResult {
  responses: Record<string, LoadedResponse>;
  /** Request full text for a turn currently represented by an excerpt. */
  expand(turn_id: string): void;
}

interface QueuedRequest {
  runId: string;
  turn: Turn;
  full: boolean;
  excerptBudget: number;
  key: string;
}

const DEFAULT_EAGER_WINDOW = 12;
const DEFAULT_EXCERPT_BUDGET = 800;
const MAX_CONCURRENT_REQUESTS = 4;

function requestKey(runId: string, turnId: string, full: boolean): string {
  return `${runId}:${turnId}:${full ? "full" : "excerpt"}`;
}

export function useTurnResponses({
  run_id,
  turns,
  eagerWindow = DEFAULT_EAGER_WINDOW,
  excerptBudget = DEFAULT_EXCERPT_BUDGET,
}: UseTurnResponsesOptions): UseTurnResponsesResult {
  const [responses, setResponses] = useState<Record<string, LoadedResponse>>({});
  const activeRunRef = useRef<string | null>(run_id);
  const queueRef = useRef<QueuedRequest[]>([]);
  const activeCountRef = useRef(0);
  const pendingRef = useRef<Set<string>>(new Set());
  const completedRef = useRef<Set<string>>(new Set());
  const drainRef = useRef<() => void>(() => undefined);

  const executeRequest = useCallback(async (request: QueuedRequest): Promise<void> => {
    const { runId, turn, full, excerptBudget: budget } = request;

    setResponses((prev) => {
      if (activeRunRef.current !== runId || prev[turn.turn_id]?.fullyLoaded) {
        return prev;
      }
      const existing = prev[turn.turn_id];
      if (existing?.text || existing?.loading) return prev;
      return {
        ...prev,
        [turn.turn_id]: {
          text: null,
          badge: null,
          loading: true,
          error: null,
          fullyLoaded: false,
        },
      };
    });

    try {
      const raw = await readArtifactText(runId, turn.artifact_id!);
      const parsed: unknown = JSON.parse(raw);
      const delta: Record<string, unknown> =
        parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
          ? (parsed as Record<string, unknown>)
          : {};
      const { text, badge } = extractResponse(turn.actor_id, delta);
      const displayText = full || !text ? text : text.slice(0, budget);

      completedRef.current.add(request.key);
      if (full) {
        completedRef.current.add(requestKey(runId, turn.turn_id, false));
      }

      setResponses((prev) => {
        if (activeRunRef.current !== runId) return prev;
        if (prev[turn.turn_id]?.fullyLoaded && !full) return prev;
        return {
          ...prev,
          [turn.turn_id]: {
            text: displayText ?? null,
            badge: badge ?? null,
            loading: false,
            error: null,
            fullyLoaded: full,
          },
        };
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setResponses((prev) => {
        if (activeRunRef.current !== runId) return prev;
        return {
          ...prev,
          [turn.turn_id]: {
            text: prev[turn.turn_id]?.text ?? null,
            badge: prev[turn.turn_id]?.badge ?? null,
            loading: false,
            error: message,
            fullyLoaded: prev[turn.turn_id]?.fullyLoaded ?? false,
          },
        };
      });
    }
  }, []);

  const drainQueue = useCallback((): void => {
    while (
      activeCountRef.current < MAX_CONCURRENT_REQUESTS &&
      queueRef.current.length > 0
    ) {
      const request = queueRef.current.shift();
      if (!request) return;
      activeCountRef.current += 1;
      void executeRequest(request).finally(() => {
        activeCountRef.current -= 1;
        pendingRef.current.delete(request.key);
        drainRef.current();
      });
    }
  }, [executeRequest]);
  drainRef.current = drainQueue;

  const enqueue = useCallback(
    (turn: Turn, full: boolean): void => {
      if (!turn.artifact_id || run_id === null) return;
      const key = requestKey(run_id, turn.turn_id, full);
      if (completedRef.current.has(key) || pendingRef.current.has(key)) return;
      pendingRef.current.add(key);
      queueRef.current.push({
        runId: run_id,
        turn,
        full,
        excerptBudget,
        key,
      });
      drainRef.current();
    },
    [run_id, excerptBudget],
  );

  useEffect(() => {
    activeRunRef.current = run_id;
    queueRef.current = [];
    pendingRef.current.clear();
    completedRef.current.clear();
    setResponses({});
  }, [run_id]);

  useEffect(() => {
    if (run_id === null) return;
    const turnsWithArtifacts = turns.filter((turn) => turn.artifact_id);
    turnsWithArtifacts.forEach((turn, index) => {
      enqueue(turn, index < eagerWindow);
    });
  }, [run_id, turns, eagerWindow, enqueue]);

  const expand = useCallback(
    (turn_id: string): void => {
      const turn = turns.find((candidate) => candidate.turn_id === turn_id);
      if (turn) enqueue(turn, true);
    },
    [turns, enqueue],
  );

  return { responses, expand };
}
