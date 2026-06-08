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
        </div>
      </aside>
    </>
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
