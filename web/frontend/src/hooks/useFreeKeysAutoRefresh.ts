import { useEffect, useRef, useState, useCallback } from "react";
import { refreshFreeKeysCache } from "../lib/api";
import { useUiStore } from "../store/ui";

const REFRESH_INTERVAL_MS = 10 * 60 * 1000; // 10 minutes

export function useFreeKeysAutoRefresh() {
  const enabled = useUiStore((s) => s.freeKeysAutoRefresh);
  const setEnabled = useUiStore((s) => s.setFreeKeysAutoRefresh);
  const [countdown, setCountdown] = useState(0);
  const [nextRefreshAt, setNextRefreshAt] = useState<number | null>(null);
  const refreshing = useRef(false);

  const toggle = useCallback(() => {
    setEnabled(!enabled);
  }, [enabled, setEnabled]);

  const refreshNow = useCallback(async () => {
    if (refreshing.current) return;
    refreshing.current = true;
    try {
      await refreshFreeKeysCache();
    } catch {
      // background refresh failure is non-fatal
    } finally {
      refreshing.current = false;
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setCountdown(0);
      setNextRefreshAt(null);
      return;
    }

    const scheduleNext = () => {
      const next = Date.now() + REFRESH_INTERVAL_MS;
      setNextRefreshAt(next);
      setCountdown(REFRESH_INTERVAL_MS);
    };

    refreshNow();
    scheduleNext();

    const countdownId = setInterval(() => {
      setNextRefreshAt((prev) => {
        if (prev === null) return null;
        const remaining = Math.max(0, prev - Date.now());
        setCountdown(remaining);
        return prev;
      });
    }, 1000);

    const intervalId = setInterval(() => {
      refreshNow();
      scheduleNext();
    }, REFRESH_INTERVAL_MS);

    return () => {
      clearInterval(countdownId);
      clearInterval(intervalId);
    };
  }, [enabled, refreshNow]);

  const resetCountdown = useCallback(() => {
    const next = Date.now() + REFRESH_INTERVAL_MS;
    setNextRefreshAt(next);
    setCountdown(REFRESH_INTERVAL_MS);
  }, []);

  return { enabled, toggle, countdown, nextRefreshAt, refreshNow, resetCountdown } as const;
}
