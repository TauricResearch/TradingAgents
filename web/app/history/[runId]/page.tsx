"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { Runs } from "@/lib/api";
import { decisionColor, fmtDate, fmtTokens, statusColor } from "@/lib/format";
import { Markdown } from "@/components/Markdown";
import { BriefPanel } from "@/components/BriefPanel";
import { ChartComparison } from "@/components/ChartComparison";
import { ChatPanel } from "@/components/ChatPanel";
import { ExportPanel } from "@/components/ExportPanel";

const SECTION_TABS = [
  { key: "market_report", label: "Market" },
  { key: "sentiment_report", label: "Sentiment" },
  { key: "news_report", label: "News" },
  { key: "fundamentals_report", label: "Fundamentals" },
  { key: "_debate", label: "Bull vs Bear" },
  { key: "_research_judge", label: "Research Mgr" },
  { key: "trader_investment_plan", label: "Trader Plan" },
  { key: "_risk", label: "Risk Debate" },
  { key: "final_trade_decision", label: "Final Decision" },
];

export default function RunDetailPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;
  const q = useQuery({
    queryKey: ["run", runId],
    queryFn: () => Runs.get(runId),
    enabled: !!runId,
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 3_000 : false,
  });
  const [tab, setTab] = useState<string>("market_report");

  const run = q.data;
  if (q.isLoading) return <div className="text-muted">Loading...</div>;
  if (!run) return <div className="text-danger">Run not found.</div>;

  const status = (run.status ?? "").toLowerCase();
  const isDone = status === "done";
  const isRunning = status === "running";
  const isError = status === "error";
  const state = run.state ?? {};
  const hasState = Object.keys(state).length > 0;
  const debate = state.investment_debate_state || {};
  const risk = state.risk_debate_state || {};

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <Link href="/history" className="text-sm text-accent hover:underline">
          &larr; Back to history
        </Link>
        <h1 className="text-2xl font-bold">
          {run.ticker} <span className="text-muted">- {run.trade_date}</span>
        </h1>
        <div className="text-sm flex items-center gap-3">
          <span className={`text-lg font-bold ${decisionColor(run.decision)}`}>
            {run.decision ?? "-"}
          </span>
          <span className={`pill ${statusColor(run.status)}`}>{run.status}</span>
          <span className="text-muted">
            {run.provider ?? "-"}/{run.deep_model ?? "-"}
          </span>
          <span className="text-muted">
            {fmtTokens(run.tokens_in)} in / {fmtTokens(run.tokens_out)} out tok
          </span>
          <span className="text-muted ml-auto">{fmtDate(run.started_at)}</span>
        </div>
      </header>

      {isError && (
        <section className="card border-danger/40 bg-danger/5 space-y-2">
          <h2 className="text-lg font-semibold text-danger">Run failed</h2>
          <div className="whitespace-pre-wrap text-sm">
            {run.error_message || "No error message was recorded."}
          </div>
          {run.error_log_path && (
            <div className="text-xs text-muted">
              Error log: <span className="font-mono">{run.error_log_path}</span>
            </div>
          )}
        </section>
      )}

      {isRunning && (
        <section className="card text-sm text-muted">
          This run is still in progress. Diagnostics will update after the run finishes.
        </section>
      )}

      {isDone && hasState && (
        <>
          <section>
            <h2 className="text-lg font-semibold mb-3">Plain-English brief</h2>
            <BriefPanel runId={run.run_id} />
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3">vs S&amp;P 500 / Nasdaq-100</h2>
            <ChartComparison ticker={run.ticker} tradeDate={run.trade_date} />
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3">Files</h2>
            <ExportPanel runId={run.run_id} />
          </section>
        </>
      )}

      {isDone && !hasState && (
        <section className="card text-sm text-muted">
          Transcript unavailable for this run. Brief, chart, export, and chat controls need the saved transcript.
        </section>
      )}

      {(hasState || isDone) && (
        <section>
          <h2 className="text-lg font-semibold mb-3">Full transcript</h2>
          {!hasState ? (
            <div className="card text-sm text-muted">
              Transcript unavailable for this run.
            </div>
          ) : (
            <>
              <div className="flex flex-wrap gap-1 border-b border-border mb-3">
                {SECTION_TABS.map((t) => {
                  const ok =
                    t.key === "_debate"
                      ? !!(debate.bull_history || debate.bear_history)
                      : t.key === "_research_judge"
                        ? !!debate.judge_decision
                        : t.key === "_risk"
                          ? !!(risk.aggressive_history || risk.conservative_history || risk.neutral_history)
                          : !!state[t.key];
                  return (
                    <button
                      key={t.key}
                      onClick={() => setTab(t.key)}
                      className={`px-3 py-1.5 text-sm border-b-2 transition-colors ${
                        tab === t.key
                          ? "border-accent text-accent"
                          : "border-transparent text-muted hover:text-fg"
                      }`}
                    >
                      {ok && <span className="mr-1 text-success">*</span>}
                      {t.label}
                    </button>
                  );
                })}
              </div>

              <div className="card">
                {tab === "_debate" ? (
                  <div className="grid sm:grid-cols-2 gap-6">
                    <div>
                      <h3 className="font-semibold mb-2">Bull</h3>
                      <Markdown>{debate.bull_history}</Markdown>
                    </div>
                    <div>
                      <h3 className="font-semibold mb-2">Bear</h3>
                      <Markdown>{debate.bear_history}</Markdown>
                    </div>
                  </div>
                ) : tab === "_research_judge" ? (
                  <Markdown>{debate.judge_decision}</Markdown>
                ) : tab === "_risk" ? (
                  <div className="space-y-4">
                    <div>
                      <h3 className="font-semibold mb-2">Aggressive</h3>
                      <Markdown>{risk.aggressive_history}</Markdown>
                    </div>
                    <div>
                      <h3 className="font-semibold mb-2">Conservative</h3>
                      <Markdown>{risk.conservative_history}</Markdown>
                    </div>
                    <div>
                      <h3 className="font-semibold mb-2">Neutral</h3>
                      <Markdown>{risk.neutral_history}</Markdown>
                    </div>
                    {risk.judge_decision && (
                      <div>
                        <h3 className="font-semibold mb-2">Risk judge</h3>
                        <Markdown>{risk.judge_decision}</Markdown>
                      </div>
                    )}
                  </div>
                ) : (
                  <Markdown>{state[tab]}</Markdown>
                )}
              </div>
            </>
          )}
        </section>
      )}

      {isDone && hasState && (
        <section>
          <h2 className="text-lg font-semibold mb-3">Chat about this run</h2>
          <ChatPanel runId={run.run_id} />
        </section>
      )}

      {run.tool_trace && run.tool_trace.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold mb-3">Tool calls ({run.tool_trace.length})</h2>
          <div className="card text-xs space-y-2 max-h-96 overflow-y-auto">
            {run.tool_trace.map((t, i) => (
              <div key={i} className="border-b border-border pb-2 last:border-0">
                <div className="font-mono">
                  <span className="text-accent">{t.tool}</span>
                  <span className="text-muted"> &lt;- {t.input?.slice(0, 200)}</span>
                </div>
                <div className="font-mono text-muted whitespace-pre-wrap">
                  -&gt; {(t.output ?? "").slice(0, 600)}
                  {(t.output ?? "").length > 600 ? "..." : ""}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
