/**
 * G3 - Lazy artifact content loader with an in-memory cache.
 *
 * Wraps readArtifactText so inspector tabs can pull artifact bodies on demand
 * without refetching on re-mount. The cache is module-level (cleared on page
 * reload) and keyed by `${run_id}:${artifact_id}`.
 */
import { useCallback, useEffect, useState } from "react";
import { readArtifactText } from "../api/client";

export interface UseArtifactResult {
  content: string | null;
  loading: boolean;
  error: string | null;
  reload(): void;
}

/** Module-level cache: survives across hook instances within a page session. */
const cache = new Map<string, string>();

function cacheKey(run_id: string, artifact_id: string): string {
  return `${run_id}:${artifact_id}`;
}

export function useArtifact(
  run_id: string | null,
  artifact_id: string | null,
): UseArtifactResult {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(
    run_id !== null && artifact_id !== null,
  );
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState<number>(0);

  const reload = useCallback((): void => {
    if (run_id !== null && artifact_id !== null) {
      cache.delete(cacheKey(run_id, artifact_id));
    }
    setReloadToken((n) => n + 1);
  }, [run_id, artifact_id]);

  useEffect(() => {
    if (run_id === null || artifact_id === null) {
      setContent(null);
      setLoading(false);
      setError(null);
      return;
    }
    const key = cacheKey(run_id, artifact_id);
    const cached = cache.get(key);
    if (cached !== undefined) {
      setContent(cached);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setContent(null);
    readArtifactText(run_id, artifact_id)
      .then((text: string) => {
        cache.set(key, text);
        if (!cancelled) {
          setContent(text);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : String(err);
          setError(message);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [run_id, artifact_id, reloadToken]);

  return { content, loading, error, reload };
}
