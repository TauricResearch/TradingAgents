"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Runs, SettingsApi } from "@/lib/api";
import { decisionColor, fmtDate, fmtTokens, statusColor } from "@/lib/format";

export default function Home() {
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => Runs.list() });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => SettingsApi.get() });

  const runsList = runs.data ?? [];
  const errored = runsList.filter((r) => r.status === "error");
  const keysSet = (settings.data?.api_keys ?? []).filter(
    (k) => k.set_in_env || k.set_in_config,
  ).length;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-bold">TradingAgents</h1>
        <p className="text-muted text-sm">
          Multi-agent LLM analysis for a single ticker on a single date.
          Decisions are recommendations, not orders.
        </p>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Metric label="API keys configured" value={keysSet} />
        <Metric label="Runs (DB)" value={runsList.length} note={errored.length ? `${errored.length} errored` : undefined} />
        <Metric label="Decisions BUY/SELL/HOLD" value={
          runsList.filter((r) => r.decision).length
        } />
        <Metric label="Errored" value={errored.length} accent={errored.length > 0 ? "danger" : undefined} />
      </section>

      <div className="grid lg:grid-cols-[3fr_2fr] gap-6">
        <section>
          <h2 className="text-lg font-semibold mb-3">Recent runs</h2>
          {runs.isLoading && <div className="text-muted text-sm">Loading…</div>}
          {!runs.isLoading && runsList.length === 0 && (
            <div className="card text-sm text-muted">
              No runs yet.{" "}
              <Link className="text-accent" href="/run">
                Start one in Run.
              </Link>
            </div>
          )}
          <div className="divide-y divide-border">
            {runsList.slice(0, 8).map((r) => (
              <Link
                key={r.run_id}
                href={`/history/${r.run_id}`}
                className="flex items-center justify-between gap-2 py-2.5 hover:bg-surface px-2 rounded-md"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-sm">
                    <span className="font-semibold">{r.ticker}</span>
                    <span className="text-muted"> · {r.trade_date} · </span>
                    <span className="text-muted">
                      {(r.provider ?? "—") + "/" + (r.deep_model ?? "—")}
                    </span>
                  </div>
                  <div className="text-xs text-muted mt-0.5">
                    {fmtTokens(r.tokens_in)}↑ / {fmtTokens(r.tokens_out)}↓ tok ·{" "}
                    {fmtDate(r.started_at)}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={`text-sm font-semibold ${decisionColor(r.decision)}`}>
                    {r.decision ?? "—"}
                  </span>
                  <span className={`pill ${statusColor(r.status)}`}>{r.status}</span>
                </div>
              </Link>
            ))}
          </div>
        </section>

        <section className="space-y-4">
          <div className="card">
            <h3 className="font-semibold mb-2">Quick links</h3>
            <ul className="space-y-1 text-sm">
              <li>
                <Link className="text-accent hover:underline" href="/run">
                  ▶ Run a new analysis
                </Link>
              </li>
              <li>
                <Link className="text-accent hover:underline" href="/history">
                  📂 Browse history + exports
                </Link>
              </li>
              <li>
                <Link className="text-accent hover:underline" href="/settings">
                  🔑 Settings (API keys, defaults)
                </Link>
              </li>
            </ul>
          </div>

          {keysSet === 0 && (
            <div className="card border-warning/40 bg-warning/5">
              <div className="font-semibold text-warning mb-1">
                🔑 No API keys configured
              </div>
              <div className="text-sm text-muted">
                Add at least one provider key in{" "}
                <Link href="/settings" className="text-accent underline">
                  Settings
                </Link>{" "}
                before starting a run.
              </div>
            </div>
          )}

          <div className="card text-xs text-muted leading-6">
            <div className="font-semibold text-fg mb-1">Where data lives</div>
            <pre className="text-[11px] overflow-x-auto">
{`Container path:    /home/appuser/.tradingagents/
Synology bind:     /volume1/docker/tradingagents/data/
   gui_config.json   API keys + GUI defaults
   gui.db            SQLite (runs, notes, chats, briefs)
   logs/             Per-run JSON archives
   exports/          md / html / pdf / json
   memory/           Rolling decision log`}
            </pre>
          </div>
        </section>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  note,
  accent,
}: {
  label: string;
  value: number | string;
  note?: string;
  accent?: "danger" | "warning";
}) {
  return (
    <div className="card">
      <div className="text-xs text-muted">{label}</div>
      <div
        className={`text-2xl font-semibold mt-1 ${
          accent === "danger" ? "text-danger" : accent === "warning" ? "text-warning" : ""
        }`}
      >
        {value}
      </div>
      {note && <div className="text-xs text-muted mt-1">{note}</div>}
    </div>
  );
}
