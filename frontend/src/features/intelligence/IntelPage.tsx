/** Market Intelligence: regime, macro calendar, metric groups, and the
 * feed-coverage panel — unsubscribed paid feeds render locked with
 * honest copy. Weakness as trust signal. */
import { Lock } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { StatCard } from "@/components/StatCard";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SkeletonCard } from "@/components/ui/skeleton";
import { useCalendar, useCorrelations, useIntel, useOverview } from "@/lib/api/queries";
import { fmtDateTime, fmtPrice } from "@/lib/format";
import { cn } from "@/lib/utils";

const GROUPS: { title: string; names: string[] }[] = [
  {
    title: "BTC derivatives",
    names: ["FUNDING_RATE", "MARK_PRICE", "OPEN_INTEREST", "ORDERBOOK_IMBALANCE"],
  },
  {
    title: "On-chain & sentiment",
    names: ["MVRV", "ACTIVE_ADDRESSES", "REALIZED_CAP", "FEAR_GREED", "HASH_RATE"],
  },
  {
    title: "Gold cross-asset",
    names: ["DXY", "US10Y_NOMINAL", "US10Y_REAL", "XAU_XAG_CORR", "SILVER"],
  },
  {
    title: "Macro (FRED)",
    names: ["CPI_YOY", "FED_FUNDS_RATE", "PPI_YOY", "NFP"],
  },
  {
    title: "Gold positioning & vol",
    names: ["GOLD_COT_NET", "GOLD_VOL_INDEX"],
  },
];

function CorrelationMatrix() {
  const correlations = useCorrelations(30);
  if (correlations.isPending) return <SkeletonCard lines={5} />;
  if (correlations.isError || !correlations.data)
    return <EmptyState kind="error" title="Correlations unavailable" />;
  const { symbols, matrix, missing, used_days } = correlations.data;
  if (symbols.length < 2)
    return (
      <EmptyState
        kind="waiting"
        title="Not enough overlapping data"
        detail={missing.join("; ") || "need at least two series"}
      />
    );
  return (
    <div data-testid="correlation-matrix">
      <table className="w-full text-xs tabular">
        <thead>
          <tr>
            <th />
            {symbols.map((sym) => (
              <th key={sym} className="px-1 pb-1 text-right font-mono font-medium">
                {sym}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {symbols.map((row) => (
            <tr key={row}>
              <td className="pr-1 font-mono">{row}</td>
              {symbols.map((col) => {
                const value = matrix[row]?.[col];
                const strong = value != null && Math.abs(value) >= 0.5 && row !== col;
                return (
                  <td
                    key={col}
                    className={cn(
                      "px-1 py-0.5 text-right",
                      row === col && "text-fg-subtle",
                      strong && value! > 0 && "text-bull",
                      strong && value! < 0 && "text-bear",
                    )}
                  >
                    {value != null ? value.toFixed(2) : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-fg-subtle">
        Pearson on daily log returns, {used_days} shared days (computed
        server-side, deterministically).
        {missing.length > 0 && <> Unavailable: {missing.join("; ")}</>}
      </p>
    </div>
  );
}

export default function IntelPage() {
  const intel = useIntel();
  const calendar = useCalendar();
  const [majorsOnly, setMajorsOnly] = useState(true);
  const overview = useOverview();

  if (intel.isPending) return <SkeletonCard lines={8} />;
  if (intel.isError || !intel.data)
    return (
      <EmptyState
        kind="error"
        title="Intelligence feed unavailable"
        detail={String(intel.error ?? "")}
      />
    );

  const metrics = new Map(intel.data.metrics.map((m) => [m.name, m]));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Regime board</CardTitle>
          <Badge>session: {intel.data.session}</Badge>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3 text-sm">
          <Badge variant="accent" className="text-sm">
            {overview.data?.symbol ?? "—"}: {overview.data?.regime ?? "no runs yet"}
          </Badge>
          <span className="text-xs text-fg-subtle">
            as of {fmtDateTime(intel.data.as_of)} — regime is computed
            deterministically from trend/volatility inputs, never by an LLM.
          </span>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        {GROUPS.map((group) => {
          const present = group.names.filter((name) =>
            [...metrics.keys()].some((k) => k.includes(name)),
          );
          const rows = [...metrics.entries()].filter(([key]) =>
            group.names.some((name) => key.includes(name)),
          );
          return (
            <Card key={group.title}>
              <CardHeader>
                <CardTitle>{group.title}</CardTitle>
              </CardHeader>
              <CardContent>
                {present.length === 0 ? (
                  <EmptyState
                    kind="waiting"
                    title="No readings"
                    detail={
                      intel.data.missing_feeds.find((f) =>
                        group.title.toLowerCase().includes(f.split(":")[0]!.split("_")[0]!),
                      ) ?? "feed returned nothing this cycle"
                    }
                  />
                ) : (
                  <div className="grid grid-cols-2 gap-2">
                    {rows.map(([name, metric]) => (
                      <StatCard
                        key={name}
                        label={name.replaceAll("_", " ")}
                        value={
                          Math.abs(metric.value) < 0.01 && metric.value !== 0
                            ? metric.value.toExponential(2)
                            : fmtPrice(metric.value, 2)
                        }
                        sub={metric.source ?? undefined}
                      />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Cross-asset correlations (30d)</CardTitle>
        </CardHeader>
        <CardContent>
          <CorrelationMatrix />
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Economic calendar</CardTitle>
            <button
              onClick={() => setMajorsOnly(!majorsOnly)}
              aria-pressed={majorsOnly}
              data-testid="calendar-majors-toggle"
              className={cn(
                "rounded-full border px-2.5 py-0.5 text-xs font-semibold",
                majorsOnly
                  ? "border-accent bg-accent text-(--on-solid)"
                  : "border-border text-fg-subtle hover:text-fg",
              )}
            >
              {majorsOnly ? "major only" : "showing all"}
            </button>
          </CardHeader>
          <CardContent>
            {calendar.isPending ? (
              <SkeletonCard lines={4} />
            ) : (calendar.data?.releases.length ?? 0) === 0 ? (
              <EmptyState
                kind={calendar.data?.missing_feeds.length ? "waiting" : "empty"}
                title={
                  calendar.data?.missing_feeds.length
                    ? "Calendar degraded"
                    : "No releases in the window"
                }
                detail={
                  calendar.data?.missing_feeds[0] ??
                  "FRED reports nothing scheduled in the next 30 days"
                }
              />
            ) : (
              (() => {
                const all = calendar.data!.releases;
                const majors = all.filter((r) => r.major);
                const shown = majorsOnly && majors.length > 0 ? majors : all;
                const nextMajor = majors[0];
                const daysTo = (date: string) =>
                  Math.max(0, Math.round(
                    (new Date(date).getTime() - Date.now()) / 86_400_000));
                const byDate = new Map<string, typeof shown>();
                for (const release of shown) {
                  byDate.set(release.date,
                             [...(byDate.get(release.date) ?? []), release]);
                }
                return (
                  <div className="space-y-2">
                    {nextMajor && (
                      <p className="text-xs text-fg-muted" data-testid="next-major">
                        next major:{" "}
                        <span className="font-semibold">{nextMajor.release}</span>
                        {" "}in {daysTo(nextMajor.date)}d ({nextMajor.date} —
                        FRED publishes dates, not times)
                      </p>
                    )}
                    {majorsOnly && majors.length === 0 && (
                      <p className="text-xs text-stale">
                        no releases flagged major in this window — showing all
                      </p>
                    )}
                    <ul className="max-h-72 space-y-2 overflow-y-auto text-sm">
                      {[...byDate.entries()].map(([date, releases]) => (
                        <li key={date}>
                          <div className="mb-0.5 font-mono text-xs tabular text-fg-subtle">
                            {date}
                          </div>
                          <ul className="space-y-0.5">
                            {releases.map((release, i) => (
                              <li key={i}
                                  className="flex items-center justify-between gap-2 border-b border-border/40 py-0.5">
                                <span className="text-fg-muted">{release.release}</span>
                                {release.major && (
                                  <Badge variant="accent" className="px-1.5 text-[10px]">
                                    major
                                  </Badge>
                                )}
                              </li>
                            ))}
                          </ul>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })()
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Feed coverage</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {intel.data.missing_feeds.length > 0 && (
              <div>
                <div className="mb-1 text-xs font-semibold uppercase text-stale">
                  Degraded this cycle
                </div>
                <ul className="space-y-1 text-xs text-fg-muted">
                  {intel.data.missing_feeds.map((feed, i) => (
                    <li key={i}>{feed}</li>
                  ))}
                </ul>
              </div>
            )}
            <div>
              <div className="mb-1 text-xs font-semibold uppercase text-locked">
                Not subscribed
              </div>
              <ul className="space-y-1.5">
                {intel.data.unsubscribed_feeds.map((feed) => (
                  <li key={feed.name} className="flex items-center gap-2 text-sm text-locked">
                    <Lock size={13} aria-hidden="true" />
                    <span className="capitalize">{feed.name.replaceAll("_", " ")}</span>
                    <Badge variant="locked">{feed.provider}</Badge>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-fg-subtle">
                These paid feeds are not connected. Agents that depend on them
                declare it in missing_feeds and reduce claim confidence — the
                dashboard never fakes a reading it doesn't have.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
