import { useState } from "react";
import { Play, Check } from "lucide-react";
import type { WsEvent } from "../lib/events";

interface ToolTimelineProps {
  events: WsEvent[];
}

export function ToolTimeline({ events }: ToolTimelineProps) {
  const [expandedTool, setExpandedTool] = useState<string | null>(null);

  const toolEvents = events.filter(e => e.type === "tool_call" || e.type === "tool_result");

  if (toolEvents.length === 0) {
    return <div className="text-xs text-slate-600 italic py-4 text-center">No tool calls yet.</div>;
  }

  return (
    <div className="space-y-1" data-testid="tool-timeline">
      {toolEvents.map((e, i) => {
        const d = e.data as any;
        const isCall = e.type === "tool_call";
        const key = `${e.id ?? i}`;
        return (
          <div key={key}>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded text-xs border-l-2 cursor-pointer hover:brightness-125 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/50"
              onClick={() => setExpandedTool(expandedTool === key ? null : key)}>
              <span className="text-slate-600 font-mono w-12 shrink-0">{new Date(e.ts).toLocaleTimeString()}</span>
              <span className="shrink-0">
                {isCall ? <Play className="w-2.5 h-2.5 text-sky-400" fill="currentColor" /> : <Check className="w-3 h-3 text-emerald-400" />}
              </span>
              <span className="truncate">{d.tool || "unknown"} {isCall ? "()" : ""}</span>
              {!isCall && d.duration_ms != null && (
                <span className="text-slate-500 ml-auto shrink-0 font-mono">{d.duration_ms}ms</span>
              )}
            </div>
            {expandedTool === key && (
              <div className="mt-1 glass-panel p-2 text-[11px] text-slate-400 whitespace-pre-wrap ml-1 mr-1 rounded-lg">
                {isCall ? `Args: ${JSON.stringify(d.args)}` : `Result: ${JSON.stringify(d.summary)}`}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
