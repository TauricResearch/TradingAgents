import { useState, useEffect, useRef } from "react";
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
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [events.length]);

  const toggleExpand = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div ref={ref} className="h-96 overflow-y-auto rounded-lg border border-slate-200 bg-white p-3 space-y-2">
      {events.length === 0 && <p className="text-sm text-slate-400">No events yet. Click "Run analysis" to start.</p>}
      {events.map((e) => {
        const key = (e.id ?? "") + ":" + e.ts;
        const data = e.data as EventData;
        const hasReport = !!data.report_text;
        return (
          <Bubble
            key={key}
            event={e}
            expanded={expanded.has(key)}
            onToggle={hasReport ? () => toggleExpand(key) : undefined}
          />
        );
      })}
    </div>
  );
}

function Bubble({ event, expanded, onToggle }: { event: WsEvent; expanded: boolean; onToggle?: () => void }) {
  const data = event.data as EventData;
  const formatter = formatBubble[event.type];
  const text = formatter ? formatter(data) : event.type;
  const reportText = data.report_text as string | undefined;
  const canExpand = !!onToggle;

  return (
    <div
      data-testid={`event-${event.id ?? ""}`}
      className={`text-xs px-2 py-1 rounded ${colorForType[event.type] ?? "bg-slate-100 text-slate-700"} ${
        canExpand ? "cursor-pointer select-none" : ""
      }`}
      onClick={canExpand ? onToggle : undefined}
    >
      <span className="text-slate-400 mr-2">{new Date(event.ts).toLocaleTimeString()}</span>
      {text}
      {expanded && reportText && (
        <pre className="mt-2 whitespace-pre-wrap text-xs text-slate-800 bg-white/60 rounded p-2 border border-slate-200 max-h-96 overflow-y-auto">
          {reportText}
        </pre>
      )}
    </div>
  );
}

/** Extract full report text grouped by stage from analyst_completed events. */
export function useStageReports(events: WsEvent[]): { stage: string; text: string }[] {
  const seen = new Set<string>();
  const reports: { stage: string; text: string }[] = [];
  // Iterate in reverse — the latest report for each stage is the final one
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.type !== "analyst_completed") continue;
    const data = e.data as EventData;
    const stage = data.stage as string | undefined;
    const text = data.report_text as string | undefined;
    if (stage && text && !seen.has(stage)) {
      seen.add(stage);
      reports.push({ stage, text });
    }
  }
  return reports.reverse();
}
