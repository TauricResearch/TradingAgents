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
  debate_message: (d) => {
    const side = String(d.side ?? "debate");
    const text = String(d.text ?? "");
    const turn = d.turn != null ? ` [#${d.turn}]` : "";
    return `${side}${turn}: ${text.slice(0, 120)}`;
  },
  risk_message: (d) => {
    const side = String(d.side ?? "risk");
    const text = String(d.text ?? "");
    return `${side}: ${text.slice(0, 120)}`;
  },
  decision: (d) => {
    const action = d.action ?? "(none)";
    const target = d.target;
    return target == null ? `DECISION: ${action}` : `DECISION: ${action} @ ${target}`;
  },
  tool_call: (d) => `tool: ${d.tool}${d.description ? ` — ${d.description}` : ""}`,
  tool_result: (d) => `result: ${String(d.summary ?? "").slice(0, 60)}${d.error ? ` ⚠ ${d.error}` : ""}`,
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
      <div ref={ref} className="h-48 md:h-72 overflow-y-auto p-2 space-y-1">
      {events.length === 0 && <p className="text-sm text-slate-600 text-center py-8">No events yet. Click "Run analysis" to start.</p>}
      {events.map((e) => {
        const key = (e.id ?? "") + ":" + (e.ts ?? 0);
        const data = e.data as EventData;
        const hasReport = !!data.report_text;
        const hasText = !!(data.text || data.summary || data.message);
        const canExpand = hasReport || hasText || e.type === "debate_message" || e.type === "risk_message";
        return (
          <Bubble
            key={key}
            event={e}
            expanded={expanded.has(key)}
            onToggle={canExpand ? () => toggleExpand(key) : undefined}
          />
        );
      })}
      </div>
      {stats.hasRun && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 px-3 py-1.5 border-t border-slate-700/50 bg-slate-900/60 text-[10px] font-mono text-slate-500">
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
  const fullText = data.text as string | undefined;
  const fullSummary = data.summary as string | undefined;
  const fullMessage = data.message as string | undefined;
  const toolArgs = data.args as string | undefined;
  const canExpand = !!onToggle;

  let expandContent: React.ReactNode = null;
  if (expanded) {
    if (reportText) {
      expandContent = (
        <pre className="mt-2 whitespace-pre-wrap text-xs text-slate-300 bg-slate-950/60 rounded-lg p-3 border border-slate-800/50 max-h-96 overflow-y-auto">
          {reportText}
        </pre>
      );
    } else if (fullText) {
      expandContent = (
        <pre className="mt-2 whitespace-pre-wrap text-xs text-slate-300 bg-slate-950/60 rounded-lg p-3 border border-slate-800/50 max-h-96 overflow-y-auto">
          {fullText}
        </pre>
      );
    } else if (event.type === "tool_call" && toolArgs) {
      expandContent = (
        <div className="mt-2 text-xs text-slate-300 bg-slate-950/60 rounded-lg p-3 border border-slate-800/50 max-h-96 overflow-y-auto font-mono whitespace-pre-wrap">
          {typeof toolArgs === "string" ? toolArgs : JSON.stringify(toolArgs, null, 2)}
        </div>
      );
    } else if (fullSummary) {
      expandContent = (
        <div className="mt-2 text-xs text-slate-400 bg-slate-950/40 rounded-lg p-2 border border-slate-800/50">
          {fullSummary}
        </div>
      );
    } else if (fullMessage) {
      expandContent = (
        <div className="mt-2 text-xs text-slate-400 bg-slate-950/40 rounded-lg p-2 border border-slate-800/50">
          {fullMessage}
        </div>
      );
    }
  }

  return (
    <div
      data-testid={`event-${event.id ?? ""}`}
      className={`text-xs px-3 py-1.5 rounded-md border-l-2 ${
        colorForType[event.type] ?? "bg-slate-700/20 text-slate-400 border-l-slate-600"
      } ${canExpand ? "cursor-pointer select-none hover:brightness-125" : ""} transition-all`}
      onClick={canExpand ? onToggle : undefined}
    >
      <span className="text-slate-600 mr-2 font-mono text-[10px]">{new Date(event.ts).toLocaleTimeString()}</span>
      {event.type === "debate_message" && (
        <svg className="w-3 h-3 inline mr-1 -mt-0.5 text-amber-400/70" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 20.25c4.97 0 9-3.694 9-8.25s-4.03-8.25-9-8.25S3 7.444 3 12c0 2.104.859 4.023 2.273 5.48.432.447.74 1.04.586 1.641a4.483 4.483 0 0 1-.923 1.785A5.969 5.969 0 0 0 6 21c1.282 0 2.47-.402 3.445-1.087.81.22 1.668.337 2.555.337Z" />
        </svg>
      )}
      {event.type === "risk_message" && (
        <svg className="w-3 h-3 inline mr-1 -mt-0.5 text-red-400/70" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
        </svg>
      )}
      {event.type === "tool_call" && (
        <svg className="w-3 h-3 inline mr-1 -mt-0.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3-4.5 16.5" />
        </svg>
      )}
      <span className="font-medium">{text}</span>
      {expandContent}
    </div>
  );
}

/** Extract full report text grouped by stage from analyst_completed events. */
// eslint-disable-next-line react-refresh/only-export-components
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
