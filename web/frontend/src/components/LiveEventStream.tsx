import { useState, useEffect, useRef, useMemo } from "react";
import { useFocusedRunEvents } from "../hooks/useFocusedRunEvents";
import { formatDuration } from "../lib/format";
import type { WsEvent } from "../lib/events";

const colorForType: Record<string, string> = {
  analyst_started: "bg-sky-500/10 text-sky-300 border-l-sky-500",
  analyst_thinking: "bg-sky-500/5 text-sky-300/80 border-l-sky-500/50",
  analyst_completed: "bg-sky-500/8 text-sky-200 border-l-sky-400",
  tool_call: "bg-slate-700/30 text-slate-400 border-l-slate-600",
  tool_result: "bg-slate-700/20 text-slate-400 border-l-slate-600",
  debate_message: "bg-amber-500/10 text-amber-300 border-l-amber-500",
  risk_message: "bg-amber-500/10 text-amber-300 border-l-amber-500",
  decision: "bg-emerald-500/10 text-emerald-300 border-l-emerald-500",
  run_failed: "bg-red-500/10 text-red-300 border-l-red-500",
  run_finished: "bg-emerald-500/8 text-emerald-300/80 border-l-emerald-400",
  server_notice: "bg-slate-700/30 text-slate-400 border-l-slate-600",
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
  decision: (d) => {
    const action = d.action ?? "(none)";
    const target = d.target;
    return target == null ? `DECISION: ${action}` : `DECISION: ${action} @ ${target}`;
  },
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

  // Derive live stats from events (mirrors CLI footer)
  const stats = useMemo(() => {
    const startedNodes = new Set<string>();
    const completedNodes = new Set<string>();
    let toolCalls = 0;
    let llmCalls = 0;
    let firstTs: number | null = null;
    let lastTs: number | null = null;

    for (const e of events) {
      const ts = new Date(e.ts).getTime();
      if (firstTs === null || ts < firstTs) firstTs = ts;
      if (lastTs === null || ts > lastTs) lastTs = ts;

      const data = e.data as EventData;
      if (e.type === "analyst_started") {
        const node = String(data.node ?? "");
        if (node) startedNodes.add(node);
      } else if (e.type === "analyst_completed") {
        const node = String(data.node ?? "");
        if (node) completedNodes.add(node);
      } else if (e.type === "tool_call") {
        toolCalls++;
      } else if (e.type === "analyst_thinking") {
        llmCalls++;
      }
    }

    const elapsed =
      firstTs != null && lastTs != null
        ? formatDuration(lastTs - firstTs)
        : "--";

    return {
      agentsDone: completedNodes.size,
      agentsTotal: startedNodes.size,
      llmCalls,
      toolCalls,
      elapsed,
      hasRun: firstTs != null,
    };
  }, [events]);

  return (
    <div className="glass-panel" data-testid="live-event-stream">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700/50">
        <span className="section-header flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-sky-400 shadow-[0_0_4px_rgba(56,189,248,0.5)] animate-pulse" />
          Event Stream
        </span>
        <span className="text-[10px] font-mono text-slate-600">{events.length} events</span>
      </div>
      <div ref={ref} className="h-72 overflow-y-auto p-2 space-y-1">
      {events.length === 0 && <p className="text-sm text-slate-600 text-center py-8">No events yet. Click "Run analysis" to start.</p>}
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
      {stats.hasRun && (
        <div className="flex items-center gap-4 px-3 py-1.5 border-t border-slate-700/50 bg-slate-900/60 text-[10px] font-mono text-slate-500">
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500/60" />
            <span className="text-emerald-400/80 font-semibold">{stats.agentsDone}</span>
            <span className="text-slate-600">/</span>
            <span className="text-slate-400">{stats.agentsTotal}</span>
            <span className="text-slate-600">agents</span>
          </span>
          <span className="w-px h-3 bg-slate-700/50" />
          <span className="text-slate-600">LLM</span>
          <span className="text-sky-400/80">{stats.llmCalls}</span>
          <span className="w-px h-3 bg-slate-700/50" />
          <span className="text-slate-600">tools</span>
          <span className="text-amber-400/80">{stats.toolCalls}</span>
          <span className="w-px h-3 bg-slate-700/50" />
          <span className="text-slate-600">elapsed</span>
          <span className="text-slate-300">{stats.elapsed}</span>
        </div>
      )}
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
      className={`text-xs px-3 py-1.5 rounded-md border-l-2 ${
        colorForType[event.type] ?? "bg-slate-700/20 text-slate-400 border-l-slate-600"
      } ${canExpand ? "cursor-pointer select-none hover:brightness-125" : ""} transition-all`}
      onClick={canExpand ? onToggle : undefined}
    >
      <span className="text-slate-600 mr-2 font-mono text-[10px]">{new Date(event.ts).toLocaleTimeString()}</span>
      <span className="font-medium">{text}</span>
      {expanded && reportText && (
        <pre className="mt-2 whitespace-pre-wrap text-xs text-slate-300 bg-slate-950/60 rounded-lg p-3 border border-slate-800/50 max-h-96 overflow-y-auto">
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
