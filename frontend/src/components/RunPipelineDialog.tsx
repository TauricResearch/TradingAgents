/** On-demand pipeline run: pick pair + timeframe, POST, watch stage
 * progress over SSE. Honest about cost — every run makes real model
 * calls. 409 = a run is already in flight (one at a time by design). */
import { Play } from "lucide-react";
import { useState } from "react";

import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Dialog, DialogContent } from "./ui/dialog";
import { apiFetch, ApiError } from "@/lib/api/client";
import { usePipelineProgress, useUiStore } from "@/stores/ui";

const SYMBOLS = [
  { value: "XAUUSD", label: "Gold (XAUUSD)" },
  { value: "BTC-USD", label: "Bitcoin (BTC-USD)" },
] as const;
const TIMEFRAMES = ["1h", "4h", "1d"] as const;

export function RunPipelineDialog() {
  const open = useUiStore((s) => s.runDialogOpen);
  const setOpen = useUiStore((s) => s.setRunDialogOpen);
  const [symbol, setSymbol] = useState<string>("XAUUSD");
  const [timeframe, setTimeframe] = useState<string>("1h");
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const progress = usePipelineProgress();

  const start = async () => {
    setError(null);
    setStarting(true);
    try {
      await apiFetch("/api/pipeline/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, timeframe }),
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("A pipeline run is already in progress — one at a time.");
      } else if (err instanceof ApiError && err.status === 503) {
        setError("No pipeline service attached (monitor mode).");
      } else {
        setError(String(err));
      }
    } finally {
      setStarting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent
        title="Run pipeline"
        description="Full agent chain on live data — debate, critic, judge, risk gates, paper execution."
        className="max-w-sm"
      >
        <div className="space-y-3 text-sm">
          <div>
            <div className="mb-1 text-xs uppercase tracking-wide text-fg-subtle">
              Pair
            </div>
            <div className="flex gap-2">
              {SYMBOLS.map((s) => (
                <Button
                  key={s.value}
                  size="sm"
                  variant={symbol === s.value ? "default" : "outline"}
                  onClick={() => setSymbol(s.value)}
                  aria-pressed={symbol === s.value}
                >
                  {s.label}
                </Button>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-1 text-xs uppercase tracking-wide text-fg-subtle">
              Timeframe
            </div>
            <div className="flex gap-2">
              {TIMEFRAMES.map((tf) => (
                <Button
                  key={tf}
                  size="sm"
                  variant={timeframe === tf ? "default" : "outline"}
                  className="font-mono"
                  onClick={() => setTimeframe(tf)}
                  aria-pressed={timeframe === tf}
                >
                  {tf}
                </Button>
              ))}
            </div>
          </div>
          <p className="text-xs text-fg-subtle">
            One run ≈ $0.10–0.20 in model calls and takes a few minutes. The
            result lands in the run history when it completes.
          </p>
          {progress && (
            <div
              className="rounded-md border border-accent/40 bg-accent-muted px-3 py-2 text-xs"
              data-testid="pipeline-progress"
            >
              running {progress.symbol} — stage:{" "}
              <span className="font-mono">{progress.stage}</span>
            </div>
          )}
          {error && <p className="text-xs text-bear">{error}</p>}
          <Button
            className="w-full"
            disabled={starting || progress != null}
            onClick={() => void start()}
            data-testid="pipeline-start"
          >
            <Play size={13} />
            {progress ? "Run in progress…" : "Run now"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Compact inline chip for page headers while a run is in flight. */
export function PipelineProgressChip() {
  const progress = usePipelineProgress();
  if (!progress) return null;
  return (
    <Badge variant="accent" data-testid="pipeline-progress-chip">
      running {progress.symbol} · {progress.stage}
    </Badge>
  );
}
