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
} from "../lib/api";

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

export function TickerAgentDrawer({ open, onClose }: TickerAgentDrawerProps) {
  const qc = useQueryClient();

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["ticker-agent", "status"],
    queryFn: getTickerAgentStatus,
    refetchInterval: 5000,
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
                {currentStatus === "running" && status?.current_cycle_ticker && (
                  <span className="text-xs text-slate-500 ml-auto">
                    Processing <span className="font-mono text-slate-300">{status.current_cycle_ticker}</span>
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

        {/* Section 2: Accuracy Leaderboard */}
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

        {/* Section 3: Activity Log */}
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
                <div key={i} className="flex items-start gap-2 text-xs py-1 border-b border-slate-800 last:border-0">
                  <span className="text-slate-600 shrink-0 whitespace-nowrap">{new Date(entry.timestamp).toLocaleString()}</span>
                  <span className="text-slate-400">{entry.message}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-600">No activity yet.</p>
          )}
        </div>

        {/* Section 4: Capabilities & Missing */}
        <div className="glass-panel p-3 space-y-2">
          <span className="section-header">Capabilities</span>
          {caps && caps.capabilities.length > 0 && (
            <div className="space-y-1">
              {caps.capabilities.filter((c) => c.available).map((c) => (
                <div key={c.name} className="flex items-center gap-2 text-xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  <span className="text-slate-300">{c.name}</span>
                </div>
              ))}
            </div>
          )}
          {missingCaps && missingCaps.capabilities.length > 0 && (
            <>
              <span className="section-header block pt-1">Missing</span>
              <div className="space-y-1">
                {missingCaps.capabilities.map((c) => (
                  <div key={c.name} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                      <span className="text-slate-400">{c.name}</span>
                    </div>
                    <button
                      className="btn-secondary text-[10px] px-2 py-0.5"
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
