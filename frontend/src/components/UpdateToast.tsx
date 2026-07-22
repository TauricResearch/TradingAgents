/** Service-worker updates. New versions apply AUTOMATICALLY (reload) as
 * soon as nothing live would be lost — the old manual prompt repeatedly
 * stranded users on stale bundles, re-hitting bugs that were already
 * fixed. While a backtest or pipeline run is in flight the reload is
 * deferred behind the prompt instead (and the backtest page re-attaches
 * to a server-side run after reload anyway, so even that is safe). */
import { RefreshCw, X } from "lucide-react";
import { useEffect } from "react";
import { useRegisterSW } from "virtual:pwa-register/react";

import { Button } from "./ui/button";
import { useBacktestLiveStore } from "@/stores/backtestLive";
import { usePipelineProgress } from "@/stores/ui";

export function UpdateToast() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW();
  const backtestRunning = useBacktestLiveStore((s) => s.status === "running");
  const pipelineRunning = usePipelineProgress() != null;
  const busy = backtestRunning || pipelineRunning;

  useEffect(() => {
    if (needRefresh && !busy) void updateServiceWorker(true);
  }, [needRefresh, busy, updateServiceWorker]);

  if (!needRefresh || !busy) return null;
  return (
    <div
      role="status"
      className="fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-[18px] border border-border bg-surface-solid px-4 py-2.5 text-sm shadow-(--shadow-2) max-md:bottom-20"
      data-testid="update-toast"
    >
      <span>A new version is available.</span>
      <Button size="sm" onClick={() => void updateServiceWorker(true)}>
        <RefreshCw size={13} /> Refresh
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
