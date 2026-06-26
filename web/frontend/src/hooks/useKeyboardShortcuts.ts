import { useEffect, useCallback } from "react";
import { useUi } from "../store/ui";
import { startRun } from "../lib/api";

export function useKeyboardShortcuts() {
  const focused = useUi((s) => s.focusedTicker);
  const historyOpenByTicker = useUi((s) => s.historyOpenByTicker);
  const backgroundRunsOpen = useUi((s) => s.backgroundRunsOpen);
  const setHistoryOpen = useUi((s) => s.setHistoryOpen);
  const setBackgroundRunsOpen = useUi((s) => s.setBackgroundRunsOpen);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      const target = e.target;
      // Don't capture when user is typing in an input/textarea/select
      if (
        !(target instanceof HTMLElement) ||
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.isContentEditable
      ) {
        return;
      }

      switch (e.key) {
        case "Escape": {
          // Close any open drawer
          if (backgroundRunsOpen) {
            e.preventDefault();
            setBackgroundRunsOpen(false);
            return;
          }
          if (focused && historyOpenByTicker[focused]) {
            e.preventDefault();
            setHistoryOpen(focused, false);
            return;
          }
          break;
        }
        case "h":
        case "H": {
          if (!focused) return;
          e.preventDefault();
          setHistoryOpen(focused, !historyOpenByTicker[focused]);
          break;
        }
        case "r":
        case "R": {
          if (!focused) return;
          // Skip if modifier keys are held (to avoid conflict with browser refresh)
          if (e.metaKey || e.ctrlKey) return;
          e.preventDefault();
          startRun(focused, true).catch(() => {});
          break;
        }
      }
    },
    [focused, historyOpenByTicker, backgroundRunsOpen, setHistoryOpen, setBackgroundRunsOpen],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);
}
