import { useState } from "react";
import type { LlmCallRow } from "../lib/api";

interface Props {
  calls: LlmCallRow[];
}

const NODE_COLORS: Record<string, string> = {
  "Market Analyst": "#38bdf8",
  "Sentiment Analyst": "#38bdf8",
  "News Analyst": "#38bdf8",
  "Fundamentals Analyst": "#38bdf8",
  "Bull Researcher": "#fb923c",
  "Bear Researcher": "#fb923c",
  "Research Manager": "#fb923c",
  "Trader": "#fbbf24",
  "Aggressive Analyst": "#ef4444",
  "Conservative Analyst": "#ef4444",
  "Neutral Analyst": "#ef4444",
  "Portfolio Manager": "#a78bfa",
};

const TEAM_ORDER = [
  "analysts",
  "research",
  "trader",
  "risk",
  "portfolio",
] as const;

const NODE_TO_TEAM: Record<string, string> = {
  "Market Analyst": "analysts",
  "Sentiment Analyst": "analysts",
  "News Analyst": "analysts",
  "Fundamentals Analyst": "analysts",
  "Bull Researcher": "research",
  "Bear Researcher": "research",
  "Research Manager": "research",
  "Trader": "trader",
  "Aggressive Analyst": "risk",
  "Conservative Analyst": "risk",
  "Neutral Analyst": "risk",
  "Portfolio Manager": "portfolio",
};

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
}

function nodeColor(nodeName: string): string {
  return NODE_COLORS[nodeName] ?? "#64748b";
}

export function LlmTracePanel({ calls }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showPrompts, setShowPrompts] = useState(true);
  const [showResponses, setShowResponses] = useState(true);

  if (calls.length === 0) {
    return (
      <div className="text-sm text-slate-600 text-center py-8">
        No LLM calls recorded yet.
      </div>
    );
  }

  // Group by node, preserving team order
  const grouped = new Map<string, LlmCallRow[]>();
  for (const call of calls) {
    const node = call.node_name || "unknown";
    if (!grouped.has(node)) grouped.set(node, []);
    grouped.get(node)!.push(call);
  }

  const sortedNodes = Array.from(grouped.entries()).sort(([a], [b]) => {
    const ta = TEAM_ORDER.indexOf((NODE_TO_TEAM[a] ?? "") as never);
    const tb = TEAM_ORDER.indexOf((NODE_TO_TEAM[b] ?? "") as never);
    if (ta !== tb) return ta - tb;
    return (NODE_COLORS[a] ?? "").localeCompare(NODE_COLORS[b] ?? "");
  });

  return (
    <div>
      {/* Toggle controls */}
      <div className="flex items-center gap-3 px-1 mb-3 text-xs text-slate-500">
        <label className="flex items-center gap-1.5 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={showPrompts}
            onChange={() => setShowPrompts((v) => !v)}
            className="w-3 h-3 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-0"
          />
          Show prompts
        </label>
        <label className="flex items-center gap-1.5 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={showResponses}
            onChange={() => setShowResponses((v) => !v)}
            className="w-3 h-3 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-0"
          />
          Show responses
        </label>
        <span className="ml-auto text-[10px] font-mono text-slate-600">
          {calls.length} LLM calls
        </span>
      </div>

      {/* Per-node sections */}
      <div className="space-y-3">
        {sortedNodes.map(([node, nodeCalls]) => {
          const color = nodeColor(node);
          const totalTokens = nodeCalls.reduce((s, c) => s + (c.total_tokens || 0), 0);
          const totalDuration = nodeCalls.reduce((s, c) => s + (c.duration_ms || 0), 0);

          return (
            <div key={node} className="rounded-lg border border-slate-700/50 bg-slate-900/60 overflow-hidden">
              {/* Node header */}
              <div
                className="flex items-center gap-3 px-3 py-2 cursor-pointer select-none hover:bg-slate-800/40 transition-colors"
                style={{ borderLeft: `3px solid ${color}` }}
                onClick={() => setExpandedId(expandedId === node ? null : node)}
              >
                <svg
                  className={`w-3 h-3 text-slate-500 transition-transform duration-200 ${
                    expandedId === node ? "rotate-90" : ""
                  }`}
                  fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                </svg>
                <span className="text-xs font-semibold text-slate-200 min-w-[140px]">{node}</span>
                <div className="flex items-center gap-3 text-[10px] font-mono text-slate-500">
                  <span>{nodeCalls.length} calls</span>
                  <span className="w-px h-3 bg-slate-700/50" />
                  <span>{formatDuration(totalDuration)}</span>
                  <span className="w-px h-3 bg-slate-700/50" />
                  <span className="text-slate-400">{totalTokens} tokens</span>
                </div>
              </div>

              {/* Expanded call details */}
              {expandedId === node && (
                <div className="border-t border-slate-700/50">
                  {nodeCalls.map((call, i) => (
                    <CallCard
                      key={call.id}
                      call={call}
                      index={i}
                      total={nodeCalls.length}
                      showPrompt={showPrompts}
                      showResponse={showResponses}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CallCard({
  call,
  index,
  total,
  showPrompt,
  showResponse,
}: {
  call: LlmCallRow;
  index: number;
  total: number;
  showPrompt: boolean;
  showResponse: boolean;
}) {
  const [promptExpanded, setPromptExpanded] = useState(false);
  const [responseExpanded, setResponseExpanded] = useState(false);

  const hasToolCalls = call.tool_calls && call.tool_calls.length > 0;
  const promptLines = call.prompt_text ? call.prompt_text.split("\n").length : 0;
  const responseLines = call.response_text ? call.response_text.split("\n").length : 0;
  const promptTruncated = promptLines > 30;
  const responseTruncated = responseLines > 30;

  return (
    <div className="border-b border-slate-800/40 last:border-b-0">
      {/* Call metadata bar */}
      <div className="flex items-center gap-3 px-4 py-1.5 bg-slate-950/30 text-[10px] font-mono text-slate-600">
        <span className="text-slate-500">#{index + 1}/{total}</span>
        <span className="w-px h-2.5 bg-slate-700/50" />
        <span className="text-slate-400">{call.model}</span>
        {call.duration_ms > 0 && (
          <>
            <span className="w-px h-2.5 bg-slate-700/50" />
            <span>{formatDuration(call.duration_ms)}</span>
          </>
        )}
        {call.total_tokens > 0 && (
          <>
            <span className="w-px h-2.5 bg-slate-700/50" />
            <span>
              <span className="text-sky-400/60">in:</span> {call.input_tokens}
              {" "}
              <span className="text-emerald-400/60">out:</span> {call.output_tokens}
            </span>
          </>
        )}
      </div>

      {/* Prompt */}
      {showPrompt && call.prompt_text && (
        <div className="px-4 py-2 border-t border-slate-800/30">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-sky-400/60">
              Prompt
            </span>
            {promptTruncated && (
              <button
                onClick={() => setPromptExpanded((v) => !v)}
                className="text-[10px] text-sky-500 hover:text-sky-400 transition-colors"
              >
                {promptExpanded ? "Collapse" : `Show all (${promptLines} lines)`}
              </button>
            )}
          </div>
          <pre
            className={`text-[11px] leading-relaxed text-slate-300 font-mono whitespace-pre-wrap break-words ${
              !promptExpanded && promptTruncated
                ? "max-h-40 overflow-y-auto"
                : ""
            }`}
            style={{ maxHeight: !promptExpanded && promptTruncated ? "160px" : "none" }}
          >
            {call.prompt_text}
          </pre>
        </div>
      )}

      {/* Response */}
      {showResponse && call.response_text && (
        <div className="px-4 py-2 border-t border-slate-800/30">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400/60">
              Response
            </span>
            {responseTruncated && (
              <button
                onClick={() => setResponseExpanded((v) => !v)}
                className="text-[10px] text-emerald-500 hover:text-emerald-400 transition-colors"
              >
                {responseExpanded ? "Collapse" : `Show all (${responseLines} lines)`}
              </button>
            )}
          </div>
          <pre
            className={`text-[11px] leading-relaxed text-slate-300 font-mono whitespace-pre-wrap break-words ${
              !responseExpanded && responseTruncated
                ? "max-h-40 overflow-y-auto"
                : ""
            }`}
            style={{ maxHeight: !responseExpanded && responseTruncated ? "160px" : "none" }}
          >
            {call.response_text}
          </pre>
        </div>
      )}

      {/* Tool calls */}
      {hasToolCalls && (
        <div className="px-4 py-2 border-t border-slate-800/30">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-amber-400/60 block mb-1">
            Tool calls
          </span>
          <pre className="text-[11px] text-amber-300/80 font-mono whitespace-pre-wrap break-words">
            {JSON.stringify(call.tool_calls, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
