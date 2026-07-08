/** Slide-over notification center: persisted read state, mark-one /
 * mark-all. Fed by the alert stream through the backend store. */
import { useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";

import { EmptyState } from "./EmptyState";
import { Button } from "./ui/button";
import {
  markNotificationsRead,
  patchPrefs,
  useNotifications,
  usePrefs,
} from "@/lib/api/queries";
import { fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";

const TONE: Record<string, string> = {
  critical: "text-bear",
  warning: "text-neutral",
  info: "text-fg-muted",
};

export function NotificationCenter() {
  const { notificationsOpen, setNotificationsOpen } = useUiStore();
  const notifications = useNotifications();
  const prefs = usePrefs();
  const client = useQueryClient();

  if (!notificationsOpen) return null;
  const muted = new Set(prefs.data?.muted_events ?? []);
  // muting hides, never deletes — the backend keeps everything
  const items = (notifications.data?.notifications ?? []).filter(
    (note) => !muted.has(note.event),
  );
  const mutedCount = (notifications.data?.notifications ?? []).length - items.length;

  return (
    <aside
      className="fixed inset-y-0 right-0 z-50 flex w-full max-w-sm flex-col border-l border-border-strong bg-surface shadow-(--shadow-2)"
      role="dialog"
      aria-label="Notification center"
      data-testid="notification-center"
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold">
          Notifications
          {notifications.data && (
            <span className="ml-2 text-xs text-fg-subtle">
              {notifications.data.unread} unread
            </span>
          )}
        </h2>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => void markNotificationsRead(client)}
          >
            Mark all read
          </Button>
          <Button
            size="icon"
            variant="ghost"
            aria-label="Close notifications"
            onClick={() => setNotificationsOpen(false)}
          >
            <X size={15} />
          </Button>
        </div>
      </div>
      <div className="grow overflow-y-auto p-3">
        {mutedCount > 0 && (
          <p className="mb-2 text-xs text-fg-subtle">
            {mutedCount} hidden by mute rules (manage in Settings)
          </p>
        )}
        {items.length === 0 ? (
          <EmptyState kind="empty" title="All clear" detail="No notifications yet." />
        ) : (
          <ul className="space-y-2">
            {items.map((note) => (
              <li
                key={note.id}
                className={cn(
                  "rounded-md border px-3 py-2 text-sm",
                  note.read
                    ? "border-border text-fg-subtle"
                    : "border-border-strong bg-surface-2",
                )}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className={cn("text-xs uppercase", TONE[note.severity])}>
                    {note.severity} · {note.event}
                  </span>
                  <span className="flex gap-2">
                    {!note.read && (
                      <button
                        className="text-xs text-accent hover:underline"
                        onClick={() => void markNotificationsRead(client, [note.id])}
                      >
                        mark read
                      </button>
                    )}
                    {note.event && (
                      <button
                        className="text-xs text-fg-subtle hover:underline"
                        onClick={() =>
                          void patchPrefs(client, {
                            muted_events: [...muted, note.event],
                          })
                        }
                      >
                        mute type
                      </button>
                    )}
                  </span>
                </div>
                <p className={note.read ? "" : "text-fg"}>{note.text}</p>
                <div className="text-xs text-fg-subtle">{fmtDateTime(note.time)}</div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
