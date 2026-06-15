import { useEffect, useRef } from "react";
import { useUi } from "../store/ui";

const NOTIFICATION_KEY = "tradingagents-notifications-granted";

export function useRunNotifications() {
  const eventBuffer = useUi((s) => s.eventBuffer);
  const notifiedRef = useRef<Set<string>>(new Set());

  // Request permission on mount
  useEffect(() => {
    if (!("Notification" in window)) return;
    if (Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  // Watch for terminal events
  useEffect(() => {
    if (!("Notification" in window)) return;
    if (Notification.permission !== "granted") return;

    // Process only the last event (most recent)
    if (eventBuffer.length === 0) return;
    const last = eventBuffer[eventBuffer.length - 1];

    // Avoid duplicate notifications for the same event
    if (notifiedRef.current.has(last.id)) return;

    if (last.type === "run_finished") {
      notifiedRef.current.add(last.id);
      new Notification("Run completed", {
        body: `Analysis finished for run ${last.run_id}`,
        icon: "/favicon.ico",
      });
    } else if (last.type === "run_failed") {
      notifiedRef.current.add(last.id);
      const reason = (last.data as Record<string, unknown>)?.reason ?? "unknown";
      new Notification("Run failed", {
        body: `Analysis failed for run ${last.run_id}: ${reason}`,
        icon: "/favicon.ico",
      });
    }
  }, [eventBuffer]);
}
