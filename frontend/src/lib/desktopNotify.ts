/** Desktop (OS-level) notifications, fired from the SSE stream (review
 * P1.4: "an AI that finds trades but can't tap my shoulder is a dashboard,
 * not an assistant").
 *
 * Deliberate shape:
 * - opt-in only — permission is requested from an explicit button in the
 *   bell panel, never on page load;
 * - fires only while the tab is HIDDEN — a visible dashboard already shows
 *   everything, and double-noise trains people to disable notifications;
 * - tag-deduped so a reconnect replaying events doesn't stack banners.
 * True Web Push (tab fully closed) needs VAPID + server-side push and is
 * tracked separately.
 */

export function desktopNotifyState(): "unsupported" | NotificationPermission {
  if (typeof Notification === "undefined") return "unsupported";
  return Notification.permission;
}

export async function requestDesktopNotify(): Promise<boolean> {
  if (typeof Notification === "undefined") return false;
  if (Notification.permission === "granted") return true;
  try {
    return (await Notification.requestPermission()) === "granted";
  } catch {
    return false;
  }
}

export function maybeNotify(title: string, body: string, tag: string): boolean {
  if (typeof Notification === "undefined") return false;
  if (Notification.permission !== "granted") return false;
  if (typeof document !== "undefined" && document.visibilityState === "visible")
    return false;
  try {
    const note = new Notification(title, { body, tag, icon: "/favicon.svg" });
    note.onclick = () => {
      window.focus();
      note.close();
    };
    return true;
  } catch {
    return false; // some browsers require a service-worker path; degrade quietly
  }
}
