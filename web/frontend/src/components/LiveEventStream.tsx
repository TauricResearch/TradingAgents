import { useEffect, useRef } from "react";
import { useUi } from "../store/ui";
import type { WsEvent } from "../lib/events";

const colorForType: Record<string, string> = {
  analyst_started: "bg-blue-100 text-blue-900",
  analyst_thinking: "bg-blue-50 text-blue-900",
  analyst_completed: "bg-blue-50 text-blue-900",
  tool_call: "bg-slate-100 text-slate-700",
  tool_result: "bg-slate-50 text-slate-700",
  debate_message: "bg-amber-50 text-amber-900",
  risk_message: "bg-amber-50 text-amber-900",
  decision: "bg-emerald-100 text-emerald-900",
  run_failed: "bg-rose-100 text-rose-900",
  run_finished: "bg-emerald-50 text-emerald-900",
  server_notice: "bg-slate-100 text-slate-700",
};

export function LiveEventStream() {
  const events = useUi((s) => s.eventBuffer);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [events.length]);

  return (
    <div ref={ref} className="h-96 overflow-y-auto rounded-lg border border-slate-200 bg-white p-3 space-y-2">
      {events.length === 0 && <p className="text-sm text-slate-400">No events yet. Click "Run analysis" to start.</p>}
      {events.map((e) => (
        <Bubble key={(e.id ?? 0) + ":" + e.ts} event={e} />
      ))}
    </div>
  );
}

function Bubble({ event }: { event: WsEvent }) {
  const data = event.data as Record<string, unknown>;
  const text =
    event.type === "analyst_thinking" ? String(data.node ?? data.stage ?? "thinking") :
    event.type === "debate_message" ? `${data.side}: ${data.text}` :
    event.type === "decision" ? `DECISION: ${data.action} @ ${data.target}` :
    event.type === "tool_call" ? `tool: ${data.tool}` :
    event.type === "tool_result" ? `result: ${String(data.summary ?? "").slice(0, 60)}` :
    event.type === "run_failed" ? `failed: ${data.reason}` :
    event.type;
  return (
    <div
      data-testid={`event-${event.id ?? ""}`}
      className={`text-xs px-2 py-1 rounded ${colorForType[event.type] ?? "bg-slate-100 text-slate-700"}`}
    >
      <span className="text-slate-400 mr-2">{new Date(event.ts).toLocaleTimeString()}</span>
      {text}
    </div>
  );
}
