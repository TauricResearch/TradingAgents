"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AgentRail } from "@/components/AgentRail";
import { DecisionBadge } from "@/components/DecisionBadge";
import { InfoTip } from "@/components/InfoTip";
import { PriceChart } from "@/components/PriceChart";
import { StateBlock } from "@/components/StateBlock";
import { api } from "@/lib/api";
import { inr, pct, signedClass } from "@/lib/format";

const TABS = ["Overview", "Technical", "Fundamental", "Sentiment", "News", "AI Debate", "Risk", "Decision", "History"];

export default function AnalyzePage() {
  return (
    <Suspense fallback={<p className="text-mist">Loading stock desk…</p>}>
      <AnalyzeInner />
    </Suspense>
  );
}

function AnalyzeInner() {
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol);
  const router = useRouter();
  const search = useSearchParams();
  const tab = search.get("tab") || "Overview";
  const qc = useQueryClient();
  const [depth, setDepth] = useState("medium");
  const quote = useQuery({ queryKey: ["quote", symbol], queryFn: () => api.quote(symbol) });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const history = useQuery({
    queryKey: ["history", symbol],
    queryFn: () => api.listAnalysis(`?symbol=${encodeURIComponent(symbol)}`),
  });
  const latest = history.data?.items.find((item) => item.status === "completed") || history.data?.items[0];
  const detail = useQuery({
    queryKey: ["analysis", latest?.analysis_id],
    queryFn: () => api.getAnalysis(latest!.analysis_id),
    enabled: Boolean(latest?.analysis_id),
  });
  const start = useMutation({
    mutationFn: () =>
      api.startAnalysis({
        symbol,
        research_depth: depth,
        llm_provider: settings.data?.llm_provider,
        model: settings.data?.model,
        selected_analysts: [
          settings.data?.enable_technical === false ? null : "market",
          settings.data?.enable_sentiment === false ? null : "social",
          settings.data?.enable_news === false ? null : "news",
          settings.data?.enable_fundamentals === false ? null : "fundamentals",
        ].filter(Boolean),
      }),
    onSuccess: (res) => router.push(`/analyze/${encodeURIComponent(symbol)}/running?id=${res.analysis_id}`),
  });
  const watch = useMutation({
    mutationFn: () => api.addWatch(symbol),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  const reports = (detail.data?.payload?.reports || {}) as Record<string, string>;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs text-mist">{quote.data?.name || symbol} · {quote.data?.exchange || "NSE"}</p>
          <h1 className="text-3xl font-semibold">{symbol.replace(".NS", "")}</h1>
          <p className="mt-1 font-mono text-2xl tabular">
            {inr(quote.data?.price ?? null)}{" "}
            <span className={`text-base ${signedClass(quote.data?.change_percent)}`}>{pct(quote.data?.change_percent)}</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select value={depth} onChange={(e) => setDepth(e.target.value)} className="rounded-md border border-line bg-ink-800 px-2 py-2 text-sm">
            <option value="shallow">Shallow</option>
            <option value="medium">Medium</option>
            <option value="deep">Deep</option>
          </select>
          <button
            onClick={() => start.mutate()}
            className="rounded-md bg-gold px-4 py-2 text-sm font-semibold text-ink-950 disabled:opacity-50"
            disabled={start.isPending}
          >
            {start.isPending ? "Queuing…" : "ANALYZE"}
          </button>
          <button onClick={() => watch.mutate()} className="rounded-md border border-line px-3 py-2 text-sm">
            Watch
          </button>
        </div>
      </div>

      {quote.isError && (
        <StateBlock title="Unable to retrieve market data." message={(quote.error as Error).message} onRetry={() => quote.refetch()} />
      )}
      {start.isError && (
        <StateBlock title="Could not start analysis." message={(start.error as Error).message} />
      )}

      <div className="grid gap-3 md:grid-cols-3">
        <Stat label="AI DECISION" tip="Portfolio Manager rating, mapped to Buy / Hold / Sell for faster reading.">
          <DecisionBadge action={detail.data?.final_decision} />
        </Stat>
        <Stat label="CONFIDENCE" tip="Shown only when the engine reported a confidence band. Never invented.">
          <p className="text-3xl tabular">{detail.data?.confidence != null ? `${Math.round(detail.data.confidence)}%` : "—"}</p>
        </Stat>
        <Stat label="RISK" tip="Derived from the risk-team debate and final action. Not a VaR number.">
          <p className="text-3xl">{detail.data?.risk_level || "—"}</p>
        </Stat>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-line pb-2">
        {TABS.map((item) => (
          <Link
            key={item}
            href={`?tab=${encodeURIComponent(item)}`}
            className={`rounded-md px-3 py-1.5 text-sm ${tab === item ? "bg-ink-700" : "text-mist"}`}
          >
            {item}
          </Link>
        ))}
      </div>

      {tab === "Overview" && (
        <div className="space-y-4">
          <PriceChart symbol={symbol} />
          <p className="rounded-xl border border-line bg-ink-800 p-4 text-sm leading-6 text-mist">
            {detail.data?.decision?.in_plain_language ||
              "Run Analyze to have the TradingAgents desk research this name. Until then this panel stays empty on purpose."}
          </p>
        </div>
      )}
      {tab === "Technical" && <Report title="Technical / Market Analyst" body={reports.market} />}
      {tab === "Fundamental" && <Report title="Fundamentals Analyst" body={reports.fundamentals} />}
      {tab === "Sentiment" && <Report title="Sentiment Analyst" body={reports.sentiment} />}
      {tab === "News" && <Report title="News Analyst" body={reports.news} />}
      {tab === "AI Debate" && (
        <div className="grid gap-3 md:grid-cols-2">
          <Report title="Bull Researcher" body={reports.bull} />
          <Report title="Bear Researcher" body={reports.bear} />
          <div className="md:col-span-2">
            <Report title="Research Manager" body={reports.research_manager} />
          </div>
        </div>
      )}
      {tab === "Risk" && (
        <div className="grid gap-3 md:grid-cols-3">
          <Report title="Aggressive" body={reports.risk_aggressive} />
          <Report title="Neutral" body={reports.risk_neutral} />
          <Report title="Conservative" body={reports.risk_conservative} />
        </div>
      )}
      {tab === "Decision" && latest && (
        <Link href={`/runs/${latest.analysis_id}/decision`} className="block rounded-xl border border-gold/40 bg-ink-800 p-6">
          <p className="text-xs text-mist">Open full decision desk</p>
          <div className="mt-3">
            <DecisionBadge action={detail.data?.final_decision} size="lg" />
          </div>
        </Link>
      )}
      {tab === "History" && (
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full text-left text-sm">
            <thead className="bg-ink-800 text-mist">
              <tr>
                <th className="px-3 py-2">Date</th>
                <th className="px-3 py-2">Decision</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {(history.data?.items || []).map((row) => (
                <tr key={row.analysis_id} className="border-t border-line">
                  <td className="px-3 py-2">{row.analysis_date}</td>
                  <td className="px-3 py-2">
                    <DecisionBadge action={row.final_decision} size="sm" />
                  </td>
                  <td className="px-3 py-2">
                    <Link href={`/runs/${row.analysis_id}`} className="text-gold">
                      {row.status}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {detail.data && tab === "Overview" && <AgentRail agents={detail.data.agents} />}
    </div>
  );
}

function Stat({ label, tip, children }: { label: string; tip: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-ink-800 p-4">
      <p className="text-xs text-mist">
        {label}
        <InfoTip text={tip} />
      </p>
      <div className="mt-2">{children}</div>
    </div>
  );
}

function Report({ title, body }: { title: string; body?: string }) {
  return (
    <article className="rounded-xl border border-line bg-ink-800 p-4">
      <h3 className="text-sm font-medium">{title}</h3>
      <div className="mt-3 whitespace-pre-wrap text-sm leading-6 text-mist">
        {body || "No report yet. Run analysis to fill this panel from the engine — nothing is fabricated."}
      </div>
    </article>
  );
}
