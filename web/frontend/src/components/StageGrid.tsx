import { useFocusedRunEvents } from "../hooks/useFocusedRunEvents";

const STAGES = [
  { key: "market", label: "Market" },
  { key: "sentiment", label: "Sentiment" },
  { key: "news", label: "News" },
  { key: "fundamentals", label: "Fundamentals" },
  { key: "research", label: "Research" },
  { key: "risk", label: "Risk" },
  { key: "trader", label: "Trader" },
] as const;

type StageKey = (typeof STAGES)[number]["key"];

function statusFor(stage: StageKey, events: any[]): "idle" | "running" | "done" | "errored" {
  // Use the explicit stage key from analyst_completed (not a substring
  // match against the node name, which was the latent bug). analyst_started
  // is matched on the stage key via the node-name -> stage-key map,
  // which mirrors the runner's _STAGE_MAP.
  const NODE_TO_STAGE: Record<string, StageKey> = {
    "Market Analyst": "market",
    "Sentiment Analyst": "sentiment",
    "News Analyst": "news",
    "Fundamentals Analyst": "fundamentals",
    "Bull Researcher": "research",
    "Bear Researcher": "research",
    "Research Manager": "research",
    "Trader": "trader",
    "Aggressive Analyst": "risk",
    "Conservative Analyst": "risk",
    "Neutral Analyst": "risk",
  };
  const completed = events.find((e) => e.type === "analyst_completed" && e.data?.stage === stage);
  if (completed) return "done";
  const started = events.find(
    (e) => e.type === "analyst_started" && NODE_TO_STAGE[e.data?.node] === stage
  );
  if (started) return "running";
  const errored = events.find((e) => e.type === "run_failed");
  if (errored) return "errored";
  return "idle";
}

export function StageGrid() {
  const events = useFocusedRunEvents();
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2 mb-4">
      {STAGES.map((s) => {
        const status = statusFor(s.key, events);
        return (
          <div
            key={s.key}
            data-testid={`stage-${s.key}`}
            data-status={status}
            className={`rounded-lg border p-3 text-sm ${
              status === "done" ? "border-emerald-200 bg-emerald-50" :
              status === "errored" ? "border-rose-200 bg-rose-50" :
              status === "running" ? "border-blue-200 bg-blue-50 animate-pulse" :
              "border-slate-200 bg-white"
            }`}
          >
            <div className="font-medium">{s.label}</div>
            <div className="text-xs text-slate-500 mt-1">
              {status === "done" ? "✓ done" : status === "errored" ? "errored" : status === "running" ? "running…" : "queued"}
            </div>
          </div>
        );
      })}
    </div>
  );
}
