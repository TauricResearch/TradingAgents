import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  startBackgroundRun,
  getBackgroundRuns,
  cancelBackgroundRun,
  pauseBackgroundRun,
  resumeBackgroundRun,
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
  const [fallbackTickers] = useState<string[]>([focusedTicker]);

  return (
    <>
      <div
        className={`fixed inset-0 z-40 bg-black/30 transition-opacity ${
          open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        }`}
        onClick={() => setOpen(false)}
        aria-hidden
      />
      <aside
        data-testid="background-runs-drawer"
        className={`fixed inset-x-0 bottom-0 z-50 bg-white border-t shadow-[0_-8px_24px_-12px_rgba(0,0,0,0.15)] transition-transform duration-200 ${
          open ? "translate-y-0" : "translate-y-full"
        }`}
        style={{ height: "45vh" }}
        role="dialog"
        aria-label="Background past runs"
      >
        <header className="flex items-center justify-between border-b px-4 py-2">
          <h2 className="font-semibold">Background Past Runs</h2>
          <button
            onClick={() => setOpen(false)}
            aria-label="Close"
            className="p-1 hover:bg-slate-100 rounded"
          >
            x
          </button>
        </header>
        <div className="h-[calc(45vh-3rem)] overflow-y-auto p-4 space-y-4">
          <NewJobForm tickers={fallbackTickers} defaultTicker={focusedTicker} />
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
      <h3 className="font-medium mb-2">Active jobs ({active.length})</h3>
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
    <div className="rounded border p-3" data-testid={`job-card-${job.job_id}`}>
      <div className="flex items-center justify-between">
        <div className="text-sm">
          <span className="font-medium">{job.ticker}</span>
          <span className="text-slate-500">
            {" "}
            - {job.date_from} -&gt; {job.date_to} - {job.every}
          </span>
        </div>
        <StatusPill status={job.status} />
      </div>
      <div
        className="mt-2 h-2 bg-slate-200 rounded overflow-hidden"
        role="progressbar"
        aria-valuenow={job.current_index}
        aria-valuemax={job.total}
      >
        <div className="h-full bg-blue-500" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1 text-xs text-slate-600">
        {job.current_index} / {job.total} ({pct.toFixed(1)}%)
        {showEta && <span className="ml-2">ETA: {etaText}</span>}
      </div>
      <div className="mt-2 flex gap-2">
        {job.status === "running" && (
          <button
            onClick={async () => {
              await pauseBackgroundRun(job.job_id);
              onChanged();
            }}
            className="px-2 py-1 text-xs rounded bg-amber-500 text-white"
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
            className="px-2 py-1 text-xs rounded bg-blue-600 text-white"
          >
            Resume
          </button>
        )}
        <button
          onClick={async () => {
            await cancelBackgroundRun(job.job_id);
            onChanged();
          }}
          className="px-2 py-1 text-xs rounded bg-red-600 text-white"
        >
          Cancel
        </button>
      </div>
      {job.current_index > 0 && (
        <div className="mt-3 border-t pt-2" data-testid="iteration-feed">
          <div className="text-xs font-medium text-slate-500 mb-1">Recent iterations</div>
          <ul className="text-xs space-y-0.5 max-h-32 overflow-y-auto">
            {Array.from({ length: Math.min(5, job.current_index) }).map((_, i) => {
              const n = job.current_index - i;
              return (
                <li key={n} className="text-slate-700">
                  iteration {n} - completed
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
    running: "bg-blue-100 text-blue-800",
    paused: "bg-amber-100 text-amber-800",
    done: "bg-green-100 text-green-800",
    cancelled: "bg-slate-200 text-slate-700",
    error: "bg-red-100 text-red-800",
  }[status];
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${color}`}>{status}</span>
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
      <details className="rounded border p-3">
        <summary className="cursor-pointer font-medium">
          Past jobs (last {Math.min(10, past.length)})
        </summary>
        <ul className="mt-2 space-y-1 text-sm">
          {past.slice(0, 10).map((j) => (
            <li key={j.job_id} className="flex items-center gap-2">
              <span className="font-medium">{j.ticker}</span>
              <span className="text-slate-500">
                {j.date_from} -&gt; {j.date_to} - {j.every}
              </span>
              <StatusPill status={j.status} />
              <span className="text-xs text-slate-500">
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
    <details open className="rounded border p-3">
      <summary className="cursor-pointer font-medium">New job</summary>
      <form
        className="mt-3 grid grid-cols-2 gap-2 text-sm"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate({ ticker, date_from: dateFrom, date_to: dateTo, every, parallel });
        }}
      >
        <label className="flex flex-col">
          <span className="text-xs text-slate-500">Ticker</span>
          <select
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            className="border rounded px-2 py-1"
            aria-label="Ticker"
          >
            {tickers.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col">
          <span className="text-xs text-slate-500">From</span>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="border rounded px-2 py-1"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-xs text-slate-500">To</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="border rounded px-2 py-1"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-xs text-slate-500">Every</span>
          <select
            value={every}
            onChange={(e) => setEvery(e.target.value as BackgroundEvery)}
            className="border rounded px-2 py-1"
          >
            {EVERY_OPTIONS.map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col">
          <span className="text-xs text-slate-500">Parallel</span>
          <select
            value={parallel}
            onChange={(e) => setParallel(Number(e.target.value))}
            className="border rounded px-2 py-1"
          >
            {PARALLEL_OPTIONS.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
        <div className="col-span-2 flex items-center gap-2">
          <button
            type="submit"
            disabled={mutation.isPending}
            className="px-3 py-1.5 rounded bg-blue-600 text-white text-sm font-medium disabled:opacity-50"
          >
            {mutation.isPending ? "Starting..." : "Start"}
          </button>
          {error && <span className="text-sm text-red-600" role="alert">{error}</span>}
        </div>
      </form>
    </details>
  );
}
