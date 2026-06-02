import { useUi } from "../store/ui";

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
  const started = events.find((e) => e.type === "analyst_started" && e.data?.node?.toLowerCase().includes(stage));
  const completed = events.find((e) => e.type === "analyst_completed" && e.data?.stage === stage);
  if (completed) return "done";
  if (started) return "running";
  return "idle";
}

export function StageGrid() {
  const events = useUi((s) => s.eventBuffer);
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
              status === "running" ? "border-blue-200 bg-blue-50 animate-pulse" :
              "border-slate-200 bg-white"
            }`}
          >
            <div className="font-medium">{s.label}</div>
            <div className="text-xs text-slate-500 mt-1">
              {status === "done" ? "✓ done" : status === "running" ? "running…" : "queued"}
            </div>
          </div>
        );
      })}
    </div>
  );
}
