import { useState, useRef, useEffect, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getTickerAgentStatus,
  runTickerAgentCycle,
  pauseTickerAgent,
  resumeTickerAgent,
  getAccuracyLeaderboard,
  getActivityLog,
  getCapabilities,
  getMissingCapabilities,
  getTickerAgentLiveEvents,
} from "../lib/api";
import { connectTickerAgentWs, type AgentLiveEvent } from "../lib/api";

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

interface TickerAgentDrawerProps {
  open: boolean;
  onClose: () => void;
}

function statusBadgeColor(status: string): string {
  switch (status) {
    case "running": return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30 agent-pulse";
    case "paused": return "bg-amber-500/20 text-amber-300 border-amber-500/30";
    default: return "bg-slate-500/20 text-slate-300 border-slate-500/30";
  }
}

function accuracyColor(pct: number | null): string {
  if (pct == null) return "text-slate-500";
  if (pct >= 80) return "text-emerald-400";
  if (pct >= 50) return "text-amber-400";
  return "text-red-400";
}

function StepProgressBar({ currentStep }: { currentStep: number }) {
  return (
    <div className="space-y-1">
      {STEP_LABELS.map((label, i) => {
        if (i === 0) return null;
        const done = i < currentStep;
        const active = i === currentStep;
        return (
          <div key={i} className="flex items-center gap-2 text-xs">
            <div className={`shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold border transition-colors ${
              done
                ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-400"
                : active
                ? "bg-sky-500/20 border-sky-400/60 text-sky-300 animate-pulse"
                : "bg-slate-800/50 border-slate-700/50 text-slate-600"
            }`}>
              {done ? "✓" : i}
            </div>
            <span className={`${
              active ? "text-sky-300 font-medium" : done ? "text-slate-400" : "text-slate-600"
            }`}>
              {label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function LiveEventFeed({ events, currentStep }: { events: AgentLiveEvent[]; currentStep: number }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  if (currentStep === 0) return null;

  return (
    <div className="space-y-0.5 max-h-28 overflow-y-auto text-[11px] font-mono">
      {events.length === 0 && (
        <div className="text-slate-600 italic">Waiting for events...</div>
      )}
      {events.map((ev) => (
        <div key={ev.id} className="flex items-start gap-1.5 text-slate-400">
          <span className="shrink-0 text-slate-600">
            {ev.timestamp.slice(11, 19)}
          </span>
          <span className="shrink-0 text-sky-600">[{ev.step}/7]</span>
          <span className="truncate">{ev.message}</span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

export function TickerAgentDrawer({ open, onClose }: TickerAgentDrawerProps) {
  if (!open) return null;

  const qc = useQueryClient();

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["ticker-agent", "status"],
    queryFn: getTickerAgentStatus,
    refetchInterval: 5000,
  });

  const currentStatus = status?.status ?? "idle";

  const { data: liveData } = useQuery({
    queryKey: ["ticker-agent", "live-events"],
    queryFn: () => getTickerAgentLiveEvents(0),
    refetchInterval: currentStatus === "running" ? 1000 : 30000,
    enabled: currentStatus === "running",
  });

  const { data: leaderboard, isLoading: lbLoading, isError: lbError, error: lbErrorObj, refetch: lbRefetch } = useQuery({
    queryKey: ["ticker-agent", "leaderboard"],
    queryFn: getAccuracyLeaderboard,
    refetchInterval: 10000,
  });

  const { data: activityLog, isLoading: logLoading, isError: logError, error: logErrorObj, refetch: logRefetch } = useQuery({
    queryKey: ["ticker-agent", "activity", 10],
    queryFn: () => getActivityLog(10),
    refetchInterval: 10000,
  });

  const { data: caps } = useQuery({
    queryKey: ["ticker-agent", "capabilities"],
    queryFn: getCapabilities,
  });

  const { data: missingCaps } = useQuery({
    queryKey: ["ticker-agent", "missing-capabilities"],
    queryFn: getMissingCapabilities,
  });

  const runMutation = useMutation({
    mutationFn: runTickerAgentCycle,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ticker-agent"] });
    },
  });

  const pauseMutation = useMutation({
    mutationFn: pauseTickerAgent,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ticker-agent", "status"] });
    },
  });

  const resumeMutation = useMutation({
    mutationFn: resumeTickerAgent,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ticker-agent", "status"] });
    },
  });

  const steps = useMemo(() => STEP_LABELS, []);

  const currentStep = liveData?.current_step ?? status?.current_step ?? 0;
  const events = liveData?.events ?? [];

  const [wsEvents, setWsEvents] = useState<AgentLiveEvent[]>([]);

  useEffect(() => {
    const cleanup = connectTickerAgentWs((ev) => {
      setWsEvents(prev => [...prev.slice(-200), ev]);
    });
    return cleanup;
  }, []);

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

  return (
    <div
      className="fixed inset-y-0 right-0 w-full md:w-[28rem] md:max-w-full bg-slate-900 border-l border-slate-700/50 shadow-2xl shadow-black/40 z-20 flex flex-col backdrop-blur-sm"
      data-testid="ticker-agent-drawer"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/50">
        <h3 className="font-display font-semibold text-slate-200">Ticker Accuracy Agent</h3>
        <button onClick={onClose} className="text-xs text-slate-500 hover:text-slate-300 transition-colors">Close</button>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 flex flex-col overflow-y-auto p-4 space-y-4">
        {/* Section 1: Status & Controls */}
        <div className="glass-panel p-3 space-y-3">
          <span className="section-header">Status &amp; Controls</span>

          {statusLoading ? (
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded-full border-2 border-sky-500/30 border-t-sky-400 animate-spin" />
              <span className="text-xs text-slate-500">Loading status…</span>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${statusDot}`} />
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${statusBadgeColor(currentStatus)}`}>
                  {statusLabel}
                </span>
                {currentStatus === "running" && currentStep > 0 && (
                  <span className="text-xs text-slate-500 ml-auto">
                    Step <span className="font-mono text-sky-400">{currentStep}/7</span>
                  </span>
                )}
              </div>

              <div className="flex items-center gap-1.5">
                <button
                  className="btn-primary text-xs"
                  disabled={currentStatus === "running" || runMutation.isPending}
                  onClick={() => runMutation.mutate()}
                >
                  {runMutation.isPending ? "Starting…" : "Run Now"}
                </button>
                <button
                  className="btn-secondary text-xs"
                  disabled={currentStatus !== "running" || pauseMutation.isPending}
                  onClick={() => pauseMutation.mutate()}
                >
                  Pause
                </button>
                <button
                  className="btn-secondary text-xs"
                  disabled={currentStatus !== "paused" || resumeMutation.isPending}
                  onClick={() => resumeMutation.mutate()}
                >
                  Resume
                </button>
              </div>

              {currentStep > 0 && (
                <div className="text-xs text-sky-400">
                  Current: <span className="font-medium">{steps[currentStep]}</span>
                </div>
              )}

              {status?.last_run_at && (
                <div className="text-xs text-slate-500">
                  Last run: <span className="text-slate-400">{new Date(status.last_run_at).toLocaleString()}</span>
                </div>
              )}
              {status?.next_scheduled_at && (
                <div className="text-xs text-slate-500">
                  Next scheduled: <span className="text-slate-400">{new Date(status.next_scheduled_at).toLocaleString()}</span>
                </div>
              )}
            </>
          )}
        </div>

        {/* Section 2: Step Progress (only during running) */}
        {currentStatus === "running" && (
          <div className="glass-panel p-3 space-y-2">
            <span className="section-header">Step Progress</span>
            <StepProgressBar currentStep={currentStep} />
          </div>
        )}

        {/* Step Details */}
        {wsEvents.filter(e => e.event_type?.startsWith("ticker_step")).length > 0 && (
          <div className="glass-panel p-3 space-y-2">
            <span className="section-header">Step Details</span>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {wsEvents.filter(e => e.event_type?.startsWith("ticker_step"))
                .map((ev, i) => (
                  <details key={i} className="text-xs border-b border-slate-800 last:border-0 py-1">
                    <summary className="cursor-pointer text-slate-400 hover:text-slate-300">
                      Step {ev.step}: {ev.step_name}
                    </summary>
                    <div className="mt-1 text-slate-500 space-y-0.5 pl-2">
                      {ev.detail && Object.entries(ev.detail).map(([k, v]) => (
                        <div key={k} className="flex gap-2">
                          <span className="text-slate-600 shrink-0">{k}:</span>
                          <span className="text-slate-400 truncate">{JSON.stringify(v)}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                ))}
            </div>
          </div>
        )}

        {/* Section 3: Live Activity Feed (only during running) */}
        {currentStatus === "running" && (
          <div className="glass-panel p-3 space-y-2">
            <span className="section-header">Live Activity</span>
            <LiveEventFeed events={events} currentStep={currentStep} />
          </div>
        )}

        {/* LLM Strategy Call */}
        {wsEvents.filter(e => e.event_type === "ticker_llm_call").length > 0 && (
          <div className="glass-panel p-3 space-y-2">
            <span className="section-header">LLM Strategy Call</span>
            {wsEvents.filter(e => e.event_type === "ticker_llm_call").map((ev, i) => (
              <details key={i} className="text-xs">
                <summary className="cursor-pointer text-sky-400 hover:text-sky-300">
                  Strategy Call #{i + 1}
                </summary>
                <div className="mt-2 space-y-2">
                  <div>
                    <div className="text-slate-500 font-medium mb-1">Prompt:</div>
                    <pre className="bg-slate-950/60 rounded p-2 text-slate-300 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto border border-slate-800/50">
                      {ev.detail?.prompt_preview || "(no prompt)"}
                    </pre>
                  </div>
                  <div>
                    <div className="text-slate-500 font-medium mb-1">Response:</div>
                    <pre className="bg-slate-950/60 rounded p-2 text-slate-300 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto border border-slate-800/50">
                      {JSON.stringify(ev.detail?.response, null, 2) || "(no response)"}
                    </pre>
                  </div>
                </div>
              </details>
            ))}
          </div>
        )}

        {/* Section 4: Accuracy Leaderboard */}
        <div className="glass-panel p-3 space-y-2">
          <span className="section-header">Accuracy Leaderboard</span>
          {lbLoading ? (
            <div className="flex items-center justify-center py-4">
              <div className="w-6 h-6 rounded-full border-2 border-sky-500/30 border-t-sky-400 animate-spin" />
            </div>
          ) : lbError ? (
            <div className="text-xs text-slate-400 space-y-1">
              <p>Failed to load: <span className="font-mono text-red-400">{(lbErrorObj as Error).message}</span></p>
              <button onClick={() => lbRefetch()} className="text-sky-400 hover:text-sky-300 transition-colors">Retry</button>
            </div>
          ) : leaderboard && Object.keys(leaderboard.scores).length > 0 ? (
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {Object.entries(leaderboard.scores)
                .sort(([, a], [, b]) => (b.accuracy_pct ?? 0) - (a.accuracy_pct ?? 0))
                .map(([ticker, entry]) => (
                  <div key={ticker} className="flex items-center justify-between text-xs py-1 border-b border-slate-800 last:border-0">
                    <span className="font-mono text-slate-300">{ticker}</span>
                    <div className="flex items-center gap-2">
                      <span className={`font-semibold ${accuracyColor(entry.accuracy_pct)}`}>
                        {entry.accuracy_pct != null ? `${entry.accuracy_pct.toFixed(1)}%` : "N/A"}
                      </span>
                      <span className="text-slate-600">{entry.total_runs} runs</span>
                    </div>
                  </div>
                ))}
            </div>
          ) : (
            <p className="text-xs text-slate-600">No accuracy data yet. Run a cycle to populate.</p>
          )}
        </div>

        {/* Section 5: Enhanced Activity Log */}
        <div className="glass-panel p-3 space-y-2">
          <span className="section-header">Activity Log</span>
          {logLoading ? (
            <div className="flex items-center justify-center py-4">
              <div className="w-6 h-6 rounded-full border-2 border-sky-500/30 border-t-sky-400 animate-spin" />
            </div>
          ) : logError ? (
            <div className="text-xs text-slate-400 space-y-1">
              <p>Failed to load: <span className="font-mono text-red-400">{(logErrorObj as Error).message}</span></p>
              <button onClick={() => logRefetch()} className="text-sky-400 hover:text-sky-300 transition-colors">Retry</button>
            </div>
          ) : activityLog && activityLog.entries.length > 0 ? (
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {activityLog.entries.map((entry, i) => (
                <details key={i} className="group text-xs border-b border-slate-800 last:border-0 py-1">
                  <summary className="flex items-start gap-2 cursor-pointer text-slate-400 hover:text-slate-300">
                    <span className="text-slate-600 shrink-0 whitespace-nowrap">{new Date(entry.timestamp).toLocaleString()}</span>
                    <span className="line-clamp-1">{entry.message}</span>
                  </summary>
                  <div className="mt-1 ml-0 space-y-0.5 text-[11px] text-slate-500 pl-0">
                    {"tickers_analyzed" in entry && entry.tickers_analyzed != null && (
                      <div>Tickers analyzed: {entry.tickers_analyzed}</div>
                    )}
                    {"backtests_scheduled" in entry && entry.backtests_scheduled != null && (
                      <div>Backtests scheduled: {entry.backtests_scheduled}</div>
                    )}
                    {"cycle" in entry && entry.cycle != null && (
                      <div>Cycle: {entry.cycle}</div>
                    )}
                    {"reasoning" in entry && entry.reasoning && (
                      <div>Reasoning: {entry.reasoning}</div>
                    )}
                  </div>
                </details>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-600">No activity yet.</p>
          )}
        </div>

        {/* Section 6: Capabilities & Missing */}
        <div className="glass-panel p-3 space-y-2">
          <span className="section-header">Capabilities</span>
          {caps && caps.capabilities.length > 0 && (
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {caps.capabilities.filter((c) => c.available).map((c, i) => (
                <div key={`${i}-${c.path || c.name}`} className="flex items-center gap-2 text-xs">
                  <span className="shrink-0 w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  <span className="text-[10px] font-mono uppercase text-emerald-500 shrink-0">{c.method}</span>
                  <span className="text-slate-400 truncate" title={c.path}>{c.path}</span>
                </div>
              ))}
            </div>
          )}
          {missingCaps && missingCaps.capabilities.length > 0 && (
            <>
              <span className="section-header block pt-1">Missing</span>
              <div className="space-y-1">
                {missingCaps.capabilities.map((c, i) => (
                  <div key={`missing-${i}-${c.name}`} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
                      <span className="text-slate-400 truncate">{c.description || c.name}</span>
                    </div>
                    <button
                      className="btn-secondary text-[10px] px-2 py-0.5 shrink-0"
                      onClick={() => console.log("Implement", c.name)}
                    >
                      Implement →
                    </button>
                  </div>
                ))}
              </div>
            </>
          )}
          {(!caps || caps.capabilities.length === 0) && (!missingCaps || missingCaps.capabilities.length === 0) && (
            <p className="text-xs text-slate-600">No capability data available.</p>
          )}
        </div>
      </div>
    </div>
  );
}