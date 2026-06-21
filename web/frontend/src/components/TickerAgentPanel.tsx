import { useState, useEffect, useMemo, useRef } from "react";
import { connectTickerAgentWs, getTickerAgentStatus, getAccuracyLeaderboard, type AgentLiveEvent } from "../lib/api";

const STEP_LABELS = [
  "Idle",
  "Read Memory",
  "Gather Context",
  "LLM Strategy",
  "Execute",
  "Rank & Reflect",
  "Write Memory",
  "Self-Improvement",
];

function accuracyColor(pct: number | null): string {
  if (pct == null) return "text-slate-500";
  if (pct >= 80) return "text-emerald-400";
  if (pct >= 50) return "text-amber-400";
  return "text-red-400";
}

interface TickerAgentPanelProps {
  onClose?: () => void;
}

export function TickerAgentPanel({ onClose }: TickerAgentPanelProps) {
  const [status, setStatus] = useState<{ status: string; last_run_at?: string; next_scheduled_at?: string; cycles_completed: number; current_step: number } | null>(null);
  const [wsEvents, setWsEvents] = useState<AgentLiveEvent[]>([]);
  const [leaderboard, setLeaderboard] = useState<{ scores: Record<string, { accuracy_pct: number | null; total_runs: number }> } | null>(null);

  useEffect(() => {
    getTickerAgentStatus().then(setStatus).catch(() => {});
    getAccuracyLeaderboard().then(setLeaderboard).catch(() => {});

    const cleanup = connectTickerAgentWs((ev) => {
      setWsEvents(prev => [...prev.slice(-500), ev]);
    });
    return cleanup;
  }, []);

  const cycleTrace = useMemo(() => {
    const started = wsEvents.filter(e => e.event_type === "ticker_step_started");
    const completed = wsEvents.filter(e => e.event_type === "ticker_step_completed");
    const steps: { step: number; name: string; durationMs: number; status: string; detail: Record<string, unknown> }[] = [];
    for (let s = 1; s <= 7; s++) {
      const startEv = [...started].reverse().find(e => e.step === s);
      const endEv = [...completed].reverse().find(e => e.step === s);
      if (!startEv && !endEv) continue;
      let durationMs = 0;
      if (startEv && endEv) {
        durationMs = new Date(endEv.timestamp).getTime() - new Date(startEv.timestamp).getTime();
      }
      steps.push({
        step: s,
        name: endEv?.step_name ?? startEv?.step_name ?? STEP_LABELS[s] ?? "",
        durationMs: Math.max(durationMs, 0),
        status: endEv ? "completed" : "running",
        detail: (endEv?.detail || startEv?.detail) as Record<string, unknown> || {},
      });
    }
    const totalMs = steps.reduce((s, st) => s + st.durationMs, 0);
    return { steps, totalMs };
  }, [wsEvents]);

  const cycleStarted = wsEvents.find(e => e.event_type === "ticker_cycle_started");
  const currentStatus = status?.status ?? "idle";

  let statusLabel: string;
  let statusDot: string;
  switch (currentStatus) {
    case "running":
      statusLabel = "Running";
      statusDot = "bg-emerald-400 agent-pulse";
      break;
    case "paused":
      statusLabel = "Paused";
      statusDot = "bg-amber-400";
      break;
    default:
      statusLabel = "Idle";
      statusDot = "bg-slate-400";
  }

  const llmCallEvents = wsEvents.filter(e => e.event_type === "ticker_llm_call");
  const dataFetchEvents = wsEvents.filter(e => e.event_type === "ticker_data_fetch");

  return (
    <div className="space-y-3 text-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${statusDot}`} />
          <span className="text-slate-300 font-medium">{statusLabel}</span>
          <span className="text-slate-500">
            {cycleStarted ? `Cycle ${cycleStarted.detail?.cycle_number}` : `Cycles: ${status?.cycles_completed ?? 0}`}
          </span>
        </div>
        {onClose && (
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300">Close</button>
        )}
      </div>

      {status?.last_run_at && (
        <div className="text-slate-500">
          Last run: <span className="text-slate-400">{new Date(status.last_run_at).toLocaleString()}</span>
        </div>
      )}

      {cycleTrace.steps.length > 0 && (
        <div className="space-y-2">
          <div className="text-slate-400 font-medium">Cycle Timeline</div>
          <div className="space-y-1">
            {cycleTrace.steps.map((st) => {
              const pct = cycleTrace.totalMs > 0 ? (st.durationMs / cycleTrace.totalMs) * 100 : 0;
              return (
                <div key={st.step} className="text-[11px]">
                  <div className="flex items-center justify-between text-slate-400 mb-0.5">
                    <span className="font-medium text-slate-300 truncate mr-2">{st.step}. {st.name}</span>
                    <span className="font-mono text-slate-500 shrink-0">{st.durationMs}ms</span>
                  </div>
                  <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full transition-all duration-300 ${
                      st.status === "completed" ? "bg-emerald-500" : "bg-sky-400 animate-pulse"
                    }`} style={{ width: `${Math.max(pct, 2)}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
          {cycleTrace.totalMs > 0 && (
            <div className="text-slate-500 pt-1 border-t border-slate-700/50 flex justify-between">
              <span>Total</span>
              <span className="font-mono text-slate-400">{(cycleTrace.totalMs / 1000).toFixed(1)}s</span>
            </div>
          )}
        </div>
      )}

      {llmCallEvents.length > 0 && (
        <div className="space-y-2">
          <div className="text-slate-400 font-medium">LLM Strategy Call</div>
          {llmCallEvents.map((ev, i) => (
            <details key={i} className="border border-slate-700/50 rounded p-2">
              <summary className="cursor-pointer text-sky-400 hover:text-sky-300">
                Strategy Call #{i + 1} - {ev.detail?.model || "unknown model"} ({ev.detail?.tokens || 0} tokens)
              </summary>
              <div className="mt-2 space-y-2">
                <div>
                  <div className="text-slate-500 font-medium mb-1">Prompt:</div>
                  <pre className="bg-slate-950/60 rounded p-2 text-slate-300 whitespace-pre-wrap font-mono max-h-32 overflow-y-auto border border-slate-800/50 text-[10px]">
                    {(ev.detail?.prompt_text as string || "(no prompt)").slice(0, 1000)}...
                  </pre>
                </div>
                <div>
                  <div className="text-slate-500 font-medium mb-1">Response:</div>
                  <pre className="bg-slate-950/60 rounded p-2 text-slate-300 whitespace-pre-wrap font-mono max-h-32 overflow-y-auto border border-slate-800/50 text-[10px]">
                    {JSON.stringify(ev.detail?.response_text || ev.detail?.response, null, 2)?.slice(0, 500)}...
                  </pre>
                </div>
              </div>
            </details>
          ))}
        </div>
      )}

      {dataFetchEvents.length > 0 && (
        <div className="space-y-2">
          <div className="text-slate-400 font-medium">Data Fetches</div>
          <div className="max-h-32 overflow-y-auto space-y-0.5">
            {dataFetchEvents.slice(-20).map((ev, i) => (
              <div key={i} className="flex items-center gap-2 text-slate-400 text-[10px]">
                <span className={ev.detail?.success ? "text-emerald-400" : "text-red-400"}>
                  {ev.detail?.success ? "✓" : "✗"}
                </span>
                <span className="font-mono text-slate-500">{ev.detail?.source}</span>
                {ev.detail?.ticker && <span className="font-mono">{ev.detail?.ticker}</span>}
                <span className="text-slate-600 ml-auto">{ev.detail?.duration_ms}ms</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2">
        <div className="text-slate-400 font-medium">Accuracy Leaderboard</div>
        {leaderboard && Object.keys(leaderboard.scores).length > 0 ? (
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {Object.entries(leaderboard.scores)
              .sort(([, a], [, b]) => (b.accuracy_pct ?? 0) - (a.accuracy_pct ?? 0))
              .slice(0, 10)
              .map(([ticker, entry]) => (
                <div key={ticker} className="flex items-center justify-between text-xs py-0.5 border-b border-slate-800/50 last:border-0">
                  <span className="font-mono text-slate-300">{ticker}</span>
                  <div className="flex items-center gap-2">
                    <span className={`font-semibold ${accuracyColor(entry.accuracy_pct)}`}>
                      {entry.accuracy_pct != null ? `${entry.accuracy_pct.toFixed(1)}%` : "N/A"}
                    </span>
                    <span className="text-slate-600">{entry.total_runs}r</span>
                  </div>
                </div>
              ))}
          </div>
        ) : (
          <p className="text-slate-600 text-[10px]">No accuracy data yet.</p>
        )}
      </div>

      <div className="space-y-2">
        <div className="text-slate-400 font-medium">Recent Events</div>
        <div className="max-h-40 overflow-y-auto space-y-0.5 font-mono text-[10px]">
          {wsEvents.slice(-50).reverse().map((ev, i) => (
            <div key={i} className="flex items-start gap-1.5 text-slate-400">
              <span className="shrink-0 text-slate-600">{ev.timestamp.slice(11, 19)}</span>
              <span className="shrink-0 text-sky-600">[{ev.step}/7]</span>
              <span className={`shrink-0 ${ev.event_type?.includes("completed") ? "text-emerald-400" : ev.event_type?.includes("started") ? "text-sky-400" : "text-slate-400"}`}>
                {ev.event_type}
              </span>
              <span className="truncate text-slate-500">{ev.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}