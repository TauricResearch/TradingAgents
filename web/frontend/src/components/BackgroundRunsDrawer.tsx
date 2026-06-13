import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  startBackgroundRun,
  getBackgroundRuns,
  cancelBackgroundRun,
  pauseBackgroundRun,
  resumeBackgroundRun,
  fetchWatchlist,
  type StartBackgroundRunRequest,
  type BackgroundEvery,
  type BackgroundRunState,
} from "../lib/api";
import { fmtEta } from "../lib/format";
import { useUi } from "../store/ui";

const EVERY_OPTIONS: BackgroundEvery[] = ["1d", "1w", "2w", "1mo"];
const PARALLEL_OPTIONS = [1, 2, 4];

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}
function daysAgoIso(n: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().slice(0, 10);
}

export function BackgroundRunsDrawer({ focusedTicker }: { focusedTicker: string }) {
  const open = useUi((s) => s.backgroundRunsOpen);
  const setOpen = useUi((s) => s.setBackgroundRunsOpen);
  const { data: watchlist = [] } = useQuery({ queryKey: ["watchlist"], queryFn: fetchWatchlist });
  const tickers = watchlist.map((w) => w.ticker);

  return (
    <>
      <div
        className={`drawer-overlay ${open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"}`}
        onClick={() => setOpen(false)}
        aria-hidden
      />
      <aside
        data-testid="background-runs-drawer"
        className={`drawer-panel inset-x-0 bottom-0 border-t ${open ? "translate-y-0" : "translate-y-full"}`}
        style={{ height: "45vh" }}
        role="dialog"
        aria-label="Background past runs"
      >
        <header className="flex items-center justify-between border-b border-slate-700/50 px-5 py-3">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
            <h2 className="font-semibold text-slate-200 text-sm">Background Past Runs</h2>
          </div>
          <button
            onClick={() => setOpen(false)}
            aria-label="Close"
            className="p-1 hover:bg-slate-700/50 rounded-lg text-slate-500 hover:text-slate-300 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </header>
        <div className="h-[calc(45vh-3.5rem)] overflow-y-auto p-4 space-y-4">
          <NewJobForm tickers={tickers.length > 0 ? tickers : [focusedTicker]} defaultTicker={focusedTicker} />
          <ActiveJobs />
          <PastJobs />
        </div>
      </aside>
    </>
  );
}

function ActiveJobs() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["background-runs"],
    queryFn: () => getBackgroundRuns(),
    refetchInterval: (q) => {
      const jobs = (q.state.data?.jobs ?? []) as BackgroundRunState[];
      return jobs.some((j) => j.status === "running" || j.status === "paused") ? 2000 : false;
    },
  });
  const active = (data?.jobs ?? []).filter(
    (j) => j.status === "running" || j.status === "paused"
  );
  if (active.length === 0) return null;
  return (
    <section>
      <h3 className="section-header flex items-center gap-2 mb-3">
        <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
        Active jobs ({active.length})
      </h3>
      <ul className="space-y-2">
        {active.map((j) => (
          <li key={j.job_id}>
            <JobCard
              job={j}
              onChanged={() => qc.invalidateQueries({ queryKey: ["background-runs"] })}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

function JobCard({ job, onChanged }: { job: BackgroundRunState; onChanged: () => void }) {
  const pct = job.total ? Math.min(100, (job.current_index / job.total) * 100) : 0;
  const showEta = job.status === "running" && job.current_index < job.total;
  const etaText = job.current_index === 0 ? "Calculating..." : fmtEta(job.eta_s);
  return (
    <div className="glass-panel p-3" data-testid={`job-card-${job.job_id}`}>
      <div className="flex items-center justify-between">
        <div className="text-sm">
          <span className="font-medium text-slate-200">{job.ticker}</span>
          <span className="text-slate-500 text-xs">
            {" "}
            &middot; {job.date_from} &rarr; {job.date_to} &middot; {job.every}
          </span>
        </div>
        <StatusPill status={job.status} />
      </div>
      <div className="progress-bar mt-2" role="progressbar" aria-valuenow={job.current_index} aria-valuemax={job.total}>
        <div className="progress-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1 text-xs text-slate-500 data-text">
        {job.current_index} / {job.total} ({pct.toFixed(1)}%)
        {showEta && <span className="ml-2 text-slate-600">ETA: {etaText}</span>}
      </div>
      <div className="mt-2 flex gap-2">
        {job.status === "running" && (
          <button
            onClick={async () => {
              await pauseBackgroundRun(job.job_id);
              onChanged();
            }}
            className="px-2.5 py-1 text-xs font-medium rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/20 hover:bg-amber-500/30 transition-colors"
          >
            Pause
          </button>
        )}
        {job.status === "paused" && (
          <button
            onClick={async () => {
              await resumeBackgroundRun(job.job_id);
              onChanged();
            }}
            className="px-2.5 py-1 text-xs font-medium rounded-lg bg-sky-500/20 text-sky-400 border border-sky-500/20 hover:bg-sky-500/30 transition-colors"
          >
            Resume
          </button>
        )}
        <button
          onClick={async () => {
            await cancelBackgroundRun(job.job_id);
            onChanged();
          }}
          className="px-2.5 py-1 text-xs font-medium rounded-lg bg-red-500/20 text-red-400 border border-red-500/20 hover:bg-red-500/30 transition-colors"
        >
          Cancel
        </button>
      </div>
      {job.current_index > 0 && (
        <div className="mt-3 border-t border-slate-700/50 pt-2" data-testid="iteration-feed">
          <div className="text-[10px] font-medium text-slate-600 mb-1">Recent iterations</div>
          <ul className="text-xs space-y-0.5 max-h-32 overflow-y-auto">
            {Array.from({ length: Math.min(5, job.current_index) }).map((_, i) => {
              const n = job.current_index - i;
              return (
                <li key={n} className="text-slate-500">
                  <span className="text-slate-600">#</span>{n} — completed
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

function StatusPill({ status }: { status: BackgroundRunState["status"] }) {
  const color = {
    running: "bg-sky-500/15 text-sky-400 border-sky-500/20",
    paused: "bg-amber-500/15 text-amber-400 border-amber-500/20",
    done: "bg-emerald-500/15 text-emerald-400 border-emerald-500/20",
    cancelled: "bg-slate-600/30 text-slate-400 border-slate-600/30",
    error: "bg-red-500/15 text-red-400 border-red-500/20",
  }[status];
  return (
    <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-md border ${color}`}>{status}</span>
  );
}

function PastJobs() {
  const { data } = useQuery({
    queryKey: ["background-runs"],
    queryFn: () => getBackgroundRuns(),
  });
  const past = (data?.jobs ?? []).filter(
    (j) => j.status === "done" || j.status === "cancelled" || j.status === "error"
  );
  if (past.length === 0) return null;
  return (
    <section>
      <details className="glass-panel p-3">
        <summary className="cursor-pointer text-sm font-medium text-slate-400 hover:text-slate-300 transition-colors [&::-webkit-details-marker]:hidden">
          <span className="flex items-center gap-2">
            <svg className={`w-3 h-3 text-slate-500 transition-transform`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
            </svg>
            Past jobs (last {Math.min(10, past.length)})
          </span>
        </summary>
        <ul className="mt-2 space-y-1">
          {past.slice(0, 10).map((j) => (
            <li key={j.job_id} className="flex items-center gap-2 text-sm py-1">
              <span className="font-medium text-slate-300 text-xs">{j.ticker}</span>
              <span className="text-xs text-slate-600">
                {j.date_from} &rarr; {j.date_to} &middot; {j.every}
              </span>
              <StatusPill status={j.status} />
              <span className="text-xs data-text text-slate-600">
                {j.current_index}/{j.total}
              </span>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}

function NewJobForm({ tickers, defaultTicker }: { tickers: string[]; defaultTicker: string }) {
  const qc = useQueryClient();
  const [ticker, setTicker] = useState(defaultTicker);
  const [dateFrom, setDateFrom] = useState(daysAgoIso(30));
  const [dateTo, setDateTo] = useState(todayIso());
  const [every, setEvery] = useState<BackgroundEvery>("1d");
  const [parallel, setParallel] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (body: StartBackgroundRunRequest) => startBackgroundRun(body),
    onSuccess: () => {
      setError(null);
      qc.invalidateQueries({ queryKey: ["background-runs"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <details open className="glass-panel p-3">
      <summary className="cursor-pointer text-sm font-medium text-slate-300 hover:text-slate-200 transition-colors [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-2">
          <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          New job
        </span>
      </summary>
      <form
        className="mt-3 grid grid-cols-2 gap-2 text-sm"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate({ ticker, date_from: dateFrom, date_to: dateTo, every, parallel });
        }}
      >
        <label className="flex flex-col gap-0.5">
          <span className="text-[10px] font-medium text-slate-600 uppercase tracking-wider">Ticker</span>
          <select
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500/30"
            aria-label="Ticker"
          >
            {tickers.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="text-[10px] font-medium text-slate-600 uppercase tracking-wider">From</span>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500/30"
          />
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="text-[10px] font-medium text-slate-600 uppercase tracking-wider">To</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500/30"
          />
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="text-[10px] font-medium text-slate-600 uppercase tracking-wider">Every</span>
          <select
            value={every}
            onChange={(e) => setEvery(e.target.value as BackgroundEvery)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500/30"
          >
            {EVERY_OPTIONS.map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="text-[10px] font-medium text-slate-600 uppercase tracking-wider">Parallel</span>
          <select
            value={parallel}
            onChange={(e) => setParallel(Number(e.target.value))}
            className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500/30"
          >
            {PARALLEL_OPTIONS.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
        <div className="col-span-2 flex items-center gap-2 mt-1">
          <button
            type="submit"
            disabled={mutation.isPending}
            className="btn-primary text-xs"
          >
            {mutation.isPending ? (
              <>
                <svg className="inline w-3 h-3 mr-1.5 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" className="opacity-25" />
                  <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                </svg>
                Starting…
              </>
            ) : "Start"}
          </button>
          {error && <span className="text-xs text-red-400" role="alert">{error}</span>}
        </div>
      </form>
    </details>
  );
}
