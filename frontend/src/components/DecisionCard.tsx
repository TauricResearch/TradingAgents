/** The decision hero: action, confidence, level ladder, size, votes,
 * invalidation, strongest counterarguments, analogs. Rejections render
 * with EQUAL visual weight — honesty is the product. */
import { Link } from "react-router-dom";

import { DirectionBadge } from "./DirectionBadge";
import { Badge } from "./ui/badge";
import { EmptyState } from "./EmptyState";
import type { Recommendation } from "@/lib/api/types";
import { fmtPrice } from "@/lib/format";
import { cn } from "@/lib/utils";

function pctFrom(entry: number, price: number): string {
  const pct = ((price / entry - 1) * 100).toFixed(1);
  return `${price >= entry ? "+" : ""}${pct}%`;
}

const CHIP_TONE: Record<string, string> = {
  BUY: "bg-bull-muted ring-bull/40",
  SELL: "bg-bear-muted ring-bear/40",
  HOLD: "bg-neutral-muted ring-neutral/40",
};

/** Hero-only level ladder: labels + rounded progress bars with mono price
 * and %·size columns (reskin). Widths are decorative rank indicators. */
function LevelLadder({ rec }: { rec: Recommendation }) {
  if (rec.entry_price == null)
    return (
      <p className="text-sm text-fg-subtle">
        No levels — not a directional position.
      </p>
    );
  const tps = [...(rec.take_profits ?? [])].reverse();
  const rows: {
    label: string;
    price: number;
    detail: string;
    width: number;
    barClass: string;
    textClass: string;
  }[] = [
    ...tps.map((tp, i) => ({
      label: `TP${tps.length - i}`,
      price: tp.price,
      detail: `${pctFrom(rec.entry_price!, tp.price)} · closes ${Math.round(tp.size_fraction * 100)}%`,
      width: Math.max(38, 92 - i * 27),
      barClass: "bg-[linear-gradient(90deg,var(--bull),rgba(22,130,74,0.55))]",
      textClass: "text-bull",
    })),
    {
      label: "ENTRY",
      price: rec.entry_price,
      detail: "",
      width: 24,
      barClass: "bg-accent",
      textClass: "font-bold text-fg",
    },
    ...(rec.stop_loss != null
      ? [
          {
            label: "STOP",
            price: rec.stop_loss,
            detail: pctFrom(rec.entry_price, rec.stop_loss),
            width: 12,
            barClass: "bg-bear",
            textClass: "text-bear",
          },
        ]
      : []),
  ];
  return (
    <div className="space-y-1.5">
      {rows.map((row) => (
        <div key={row.label} className="flex items-center gap-3 text-sm">
          <span className={cn("w-12 font-mono text-xs", row.textClass)}>
            {row.label}
          </span>
          <span className="h-2 grow overflow-hidden rounded-full bg-surface-2">
            <span
              className={cn("block h-full rounded-full", row.barClass)}
              style={{ width: `${row.width}%` }}
            />
          </span>
          <span className={cn("w-24 text-right font-mono tabular", row.textClass)}>
            {fmtPrice(row.price)}
          </span>
          <span className="w-32 whitespace-nowrap text-xs text-fg-subtle">
            {row.detail}
          </span>
        </div>
      ))}
    </div>
  );
}

export function DecisionCard({
  rec,
  compact = false,
  hero = false,
  kicker,
  runId,
}: {
  rec: Recommendation | null | undefined;
  compact?: boolean;
  hero?: boolean;
  kicker?: string;
  runId?: string | null;
}) {
  if (!rec) return <EmptyState kind="waiting" title="Waiting for first decision" />;

  if (rec.status === "rejected") {
    const reasons = (rec.rejection?.reasons as string[] | undefined) ?? [];
    return (
      <div data-testid="decision-rejected">
        <div className="flex items-center gap-3">
          <span className="rounded-md bg-neutral-muted px-3 py-1 text-lg font-bold text-neutral">
            ✕ REJECTED
          </span>
          <span className="text-sm text-fg-muted">
            at {String(rec.rejection?.stage ?? "unknown stage")}
          </span>
        </div>
        {reasons.length > 0 && (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {reasons.map((reason, i) => (
              <li key={i}>{String(reason)}</li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-xs text-fg-subtle">
          A refused trade is a decision too — the gates exist to say no.
        </p>
      </div>
    );
  }

  if (rec.status) {
    return (
      <EmptyState
        kind="waiting"
        title="No runs yet"
        detail="The next pipeline run will populate this card."
      />
    );
  }

  const tally = rec.vote_tally ?? {};
  const counters = [...(rec.counterarguments ?? [])]
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, compact ? 1 : 3);
  const analogs = (rec.historical_analogs ?? []).slice(0, 2);

  return (
    <div className="space-y-3" data-testid="decision-card">
      {hero && kicker && (
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-bold uppercase tracking-[0.09em] text-fg-subtle">
            {kicker}
          </span>
          <Badge variant="accent">{rec.market_regime}</Badge>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3">
        {hero ? (
          <span
            className={cn(
              "inline-flex items-center rounded-[14px] px-4 py-1 ring-1 ring-inset",
              CHIP_TONE[rec.action ?? "HOLD"] ?? CHIP_TONE.HOLD,
            )}
          >
            <DirectionBadge value={rec.action} className="text-[28px] font-extrabold" />
          </span>
        ) : (
          <DirectionBadge value={rec.action} className="text-2xl font-bold" />
        )}
        <span
          className={cn(
            "text-sm text-fg-muted",
            hero && "border-l border-border pl-4",
          )}
        >
          confidence{" "}
          <span className={cn("font-mono tabular", hero && "text-2xl text-fg")}>
            {rec.confidence}
          </span>
          <span className="text-fg-subtle">/100</span>
        </span>
        {!hero && <Badge variant="accent">{rec.market_regime}</Badge>}
        {rec.risk_reward != null && (
          <span className={cn(hero && "border-l border-border pl-4")}>
            <Badge>R:R {rec.risk_reward.toFixed(2)}</Badge>
          </span>
        )}
      </div>

      {hero ? (
        <LevelLadder rec={rec} />
      ) : rec.entry_price != null ? (
        <table className="font-mono text-sm tabular">
          <thead className="sr-only">
            <tr>
              <th>Level</th>
              <th>Price</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {[...(rec.take_profits ?? [])].reverse().map((tp, i, arr) => (
              <tr key={`tp-${i}`} className="text-bull">
                <td className="pr-4">TP{arr.length - i}</td>
                <td className="pr-4 text-right">{fmtPrice(tp.price)}</td>
                <td className="whitespace-nowrap text-fg-subtle">
                  {pctFrom(rec.entry_price!, tp.price)}
                  {compact
                    ? ` · ${Math.round(tp.size_fraction * 100)}%`
                    : ` · closes ${Math.round(tp.size_fraction * 100)}%`}
                </td>
              </tr>
            ))}
            <tr className="font-bold">
              <td className="pr-4">ENTRY</td>
              <td className="pr-4 text-right">{fmtPrice(rec.entry_price)}</td>
              <td />
            </tr>
            {rec.stop_loss != null && (
              <tr className="text-bear">
                <td className="pr-4">STOP</td>
                <td className="pr-4 text-right">{fmtPrice(rec.stop_loss)}</td>
                <td className="text-fg-subtle">
                  {pctFrom(rec.entry_price!, rec.stop_loss)}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      ) : (
        <p className="text-sm text-fg-subtle">
          No levels — not a directional position.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        {rec.position_size && (
          <span className="tabular">
            size {rec.position_size.quantity.toFixed(4)}
            {rec.position_size.pct_of_equity != null &&
              ` (${rec.position_size.pct_of_equity}% equity)`}
          </span>
        )}
        <span>
          votes <span className="text-bull">▲{tally.BUY ?? 0}</span>{" "}
          <span className="text-neutral">–{tally.HOLD ?? 0}</span>{" "}
          <span className="text-bear">▼{tally.SELL ?? 0}</span>
        </span>
        <span className="text-fg-subtle">
          {rec.n_evidence ?? 0} evidence · {rec.n_counterarguments ?? 0} counter
        </span>
      </div>

      {rec.invalidation && (
        <div
          className="rounded-md border border-neutral/40 bg-neutral-muted px-3 py-2 text-sm"
          data-testid="invalidation"
        >
          <span className="font-semibold">Invalidation:</span> {rec.invalidation}
        </div>
      )}

      {!compact && counters.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
            Strongest counterarguments
          </div>
          <ul className="space-y-1 text-sm">
            {counters.map((c, i) => (
              <li key={i} className={cn("flex gap-2")}>
                <DirectionBadge value={c.direction} showWord={false} />
                <span>
                  <span className="font-semibold">{c.agent_id}</span>{" "}
                  <span className="text-fg-subtle">conf {c.confidence}</span> —{" "}
                  {c.claim}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!compact && analogs.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
            Historical analogs
          </div>
          <ul className="space-y-1 text-sm text-fg-muted">
            {analogs.map((analog, i) => (
              <li key={i}>
                {analog.description}{" "}
                <span className="text-fg-subtle">
                  ({Math.round(analog.similarity * 100)}% similar)
                </span>{" "}
                — {analog.outcome}
              </li>
            ))}
          </ul>
        </div>
      )}

      {runId &&
        (hero ? (
          <Link
            to={`/decisions/${runId}`}
            className="inline-flex items-center rounded-xl bg-accent px-3.5 py-2 text-sm font-semibold text-on-solid shadow-[0_8px_18px_-8px_rgba(36,86,197,0.6)] hover:bg-brand-strong"
          >
            Open full reasoning →
          </Link>
        ) : (
          <Link
            to={`/decisions/${runId}`}
            className="inline-block text-sm text-accent underline underline-offset-2"
          >
            Open full reasoning →
          </Link>
        ))}
    </div>
  );
}
