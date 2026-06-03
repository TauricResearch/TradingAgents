import { useEffect, useRef } from "react";
import { useFocusedRunEvents } from "../hooks/useFocusedRunEvents";
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

type EventData = Record<string, unknown>;
type Formatter = (data: EventData) => string;

function formatRunFailed(data: EventData): string {
  // Combinations of (reason), (exception_class), (message) — keep the
  // output stable across all four shapes so the test "shows exception
  // class and message on run_failed" stays green AND the partial-shape
  // case (e.g. just `{"reason": "cancelled"}` from a cancel) doesn't
  // emit a stray parenthesis.
  const reason = String(data.reason ?? "unknown");
  const cls = data.exception_class ? String(data.exception_class) : null;
  const msg = data.message ? String(data.message) : null;
  if (cls && msg) return `failed: ${reason} (${cls}: ${msg})`;
  if (cls) return `failed: ${reason} (${cls})`;
  if (msg) return `failed: ${reason}: ${msg}`;
  return `failed: ${reason}`;
}

const formatBubble: Record<string, Formatter> = {
  analyst_started: (d) =>
    `analyst_started: ${d.node ?? d.stage ?? "(unknown node)"}`,
  analyst_thinking: (d) => String(d.node ?? d.stage ?? "thinking"),
  analyst_completed: (d) =>
    `analyst_completed: ${d.stage ?? d.node ?? "(unknown stage)"}` +
    (d.summary ? ` — ${String(d.summary)}` : ""),
  debate_message: (d) => `${d.side}: ${d.text}`,
  risk_message: (d) => `${d.side}: ${d.text}`,
  decision: (d) => `DECISION: ${d.action} @ ${d.target}`,
  tool_call: (d) => `tool: ${d.tool}`,
  tool_result: (d) => `result: ${String(d.summary ?? "").slice(0, 60)}`,
  tool_call_warning: (d) => `warning: ${d.message ?? "(no message)"}`,
  run_failed: formatRunFailed,
};

export function LiveEventStream() {
  const events = useFocusedRunEvents();
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
  const data = event.data as EventData;
  const formatter = formatBubble[event.type];
  const text = formatter ? formatter(data) : event.type;
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
