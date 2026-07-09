/** Service-worker update prompt. registerType is "prompt": a trading UI
 * must never be silently swapped mid-session, but without this toast the
 * new version would wait forever and users would strand on stale
 * bundles (review finding: exactly that bit us during development). */
import { RefreshCw, X } from "lucide-react";
import { useRegisterSW } from "virtual:pwa-register/react";

import { Button } from "./ui/button";

export function UpdateToast() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW();

  if (!needRefresh) return null;
  return (
    <div
      role="status"
      className="fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-lg border border-border-strong bg-surface px-4 py-2.5 text-sm shadow-(--shadow-2) max-md:bottom-20"
      data-testid="update-toast"
    >
      <span>A new version of the terminal is ready.</span>
      <Button size="sm" onClick={() => void updateServiceWorker(true)}>
        <RefreshCw size={13} /> Reload
      </Button>
      <Button
        size="icon"
        variant="ghost"
        aria-label="Dismiss update notice"
        className="h-6 w-6"
        onClick={() => setNeedRefresh(false)}
      >
        <X size={13} />
      </Button>
    </div>
  );
}
