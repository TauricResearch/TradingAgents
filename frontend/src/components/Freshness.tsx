/** Per-widget freshness dot: source, last update, threshold — the honest
 * counterpart of the global LIVE/STALE strip. Users cannot hide these. */
import { relativeAge } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Tip } from "@/components/ui/tooltip";

export type FreshState = "live" | "stale" | "error" | "expected-latency";

const DOT: Record<FreshState, string> = {
  live: "bg-bull",
  stale: "bg-stale",
  error: "bg-bear",
  "expected-latency": "bg-fg-subtle",
};

export function FreshnessDot({
  state,
  source,
  updatedAt,
  note,
}: {
  state: FreshState;
  source?: string;
  updatedAt?: string | number | null;
  note?: string;
}) {
  const at =
    typeof updatedAt === "number" ? new Date(updatedAt).toISOString() : updatedAt;
  return (
    <Tip
      content={
        <div className="space-y-0.5">
          <div className="font-semibold capitalize">{state.replace("-", " ")}</div>
          {source && <div>source: {source}</div>}
          {at && <div>updated {relativeAge(at)}</div>}
          {note && <div className="text-fg-muted">{note}</div>}
        </div>
      }
    >
      <span
        className={cn("inline-block h-2 w-2 rounded-full", DOT[state])}
        role="status"
        aria-label={`data ${state}`}
      />
    </Tip>
  );
}

export function freshnessFrom(
  dataUpdatedAt: number,
  isError: boolean,
  staleAfterMs = 30_000,
): FreshState {
  if (isError) return "error";
  if (!dataUpdatedAt) return "stale";
  return Date.now() - dataUpdatedAt > staleAfterMs ? "stale" : "live";
}
