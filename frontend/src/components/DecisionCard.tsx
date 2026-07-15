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

function humanRegime(regime: string | null | undefined): string {
  return (regime ?? "unknown").replaceAll("_", " ");
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
      {/* the old table variant exposed column headers to screen readers;
          the ladder keeps that contract */}
      <div className="sr-only">Levels: label, price, detail</div>
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

/** Deterministic bet math (G9): breakeven win-rate from R:R, and the
 * dollar risk/reward implied by the ladder x size. Pure arithmetic over
 * backend-computed fields — this function derives no trading numbers of
 * its own beyond the identity 1/(1+RR). */
export function betMath(rec: Recommendation): {
  breakevenPct: number;
  riskUsd: number | null;
  rewardUsd: number | null;
} | null {
  const rr = rec.risk_reward;
  if (rr == null || rr <= 0) return null;
  const entry = rec.entry_price;
  const stop = rec.stop_loss;
  const qty = rec.position_size?.quantity;
  // take_profits is ordered closest-first (the ladder reverses for display)
  const tp1 = rec.take_profits?.[0]?.price;
  const riskUsd =
    entry != null && stop != null && qty != null
      ? Math.abs(entry - stop) * qty
      : null;
  const rewardUsd =
    entry != null && tp1 != null && qty != null
      ? Math.abs(tp1 - entry) * qty
      : null;
  return { breakevenPct: 100 / (1 + rr), riskUsd, rewardUsd };
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
    const meta = rec as { run_id?: string };
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
        {reasons.length > 0 &&
          (compact || hero ? (
            // board/rail slots stay card-sized (mockup's rejected state is
            // a short box): first reason clamped; full record one click away
            <p
              className={cn(
                "mt-2 text-sm text-fg-muted",
                hero ? "line-clamp-3" : "line-clamp-2",
              )}
            >
              {String(reasons[0])}
            </p>
          ) : (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
              {reasons.map((reason, i) => (
                <li key={i}>{String(reason)}</li>
              ))}
            </ul>
          ))}
        {(compact || hero) && (reasons.length > 1 || meta.run_id || runId) && (
          <p className="mt-1 text-xs text-fg-subtle">
            {reasons.length > 1 && `+${reasons.length - 1} more reason${reasons.length > 2 ? "s" : ""} — `}
            {(runId ?? meta.run_id) ? (
              <Link
                to={`/decisions/${runId ?? meta.run_id}`}
                className="font-semibold text-accent hover:underline"
              >
                full reasoning →
              </Link>
            ) : (
              "see the Decisions page"
            )}
          </p>
        )}
        {!compact && (
          <p className="mt-2 text-xs text-fg-subtle">
            A refused trade is a decision too — the gates exist to say no.
          </p>
        )}
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
  const math = betMath(rec);
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
          <Badge variant="accent">{humanRegime(rec.market_regime)} regime</Badge>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-4">
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
          // mockup: action sits on a filled tone pill on Decisions/Trade too
          <span
            className={cn(
              "inline-flex items-center rounded-[12px] px-3 py-0.5 ring-1 ring-inset",
              CHIP_TONE[rec.action ?? "HOLD"] ?? CHIP_TONE.HOLD,
            )}
          >
            <DirectionBadge value={rec.action} className="text-2xl font-bold" />
          </span>
        )}
        {hero ? (
          <>
            {/* mockup hero stats: small-caps label over big mono value,
                hairline dividers between stats */}
            <span className="border-l border-border pl-4">
              <span className="block text-[10.5px] text-fg-subtle">confidence</span>
              <span className="font-mono text-2xl text-fg tabular">
                {rec.confidence}
                <span className="text-sm text-fg-subtle">/100</span>
              </span>
            </span>
            {rec.risk_reward != null && (
              <span className="border-l border-border pl-4">
                <span className="block text-[10.5px] text-fg-subtle">
                  risk : reward
                </span>
                <span className="font-mono text-2xl text-fg tabular">
                  {rec.risk_reward.toFixed(2)}
                </span>
              </span>
            )}
            <span className="border-l border-border pl-4">
              <span className="block text-[10.5px] text-fg-subtle">votes</span>
              <span className="font-mono text-lg tabular">
                <span className="text-bull">▲{tally.BUY ?? 0}</span>{" "}
                <span className="text-neutral">–{tally.HOLD ?? 0}</span>{" "}
                <span className="text-bear">▼{tally.SELL ?? 0}</span>
              </span>
            </span>
          </>
        ) : (
          <>
            <span className="text-sm text-fg-muted">
              confidence{" "}
              <span className="font-mono tabular">{rec.confidence}</span>
              <span className="text-fg-subtle">/100</span>
            </span>
            <Badge variant="accent">{humanRegime(rec.market_regime)}</Badge>
            {rec.risk_reward != null && (
              <Badge>R:R {rec.risk_reward.toFixed(2)}</Badge>
            )}
          </>
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
        {!hero && (
          <span>
            votes <span className="text-bull">▲{tally.BUY ?? 0}</span>{" "}
            <span className="text-neutral">–{tally.HOLD ?? 0}</span>{" "}
            <span className="text-bear">▼{tally.SELL ?? 0}</span>
          </span>
        )}
        <span className="text-fg-subtle">
          {rec.n_evidence ?? 0} evidence · {rec.n_counterarguments ?? 0} counter
        </span>
      </div>

      {!compact && math != null && (
        <div className="text-xs text-fg-muted tabular" data-testid="bet-math">
          breakeven win rate {math.breakevenPct.toFixed(0)}% (from R:R)
          {math.riskUsd != null && math.rewardUsd != null && (
            <>
              {" "}· risking {fmtPrice(math.riskUsd, 0)} to make{" "}
              {fmtPrice(math.rewardUsd, 0)} at first target
            </>
          )}
          {" "}· stated confidence {rec.confidence ?? "—"}/100 (calibration
          builds as trades close)
        </div>
      )}

      {rec.invalidation && (
        <div
          className="rounded-xl bg-neutral-muted px-3 py-2 text-sm"
          data-testid="invalidation"
        >
          <span className="font-semibold text-neutral">Invalidation</span> —{" "}
          {rec.invalidation}
        </div>
      )}

      {!compact && !hero && counters.length > 0 && (
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

      {!compact && !hero && analogs.length > 0 && (
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
            className="inline-flex items-center rounded-xl bg-accent px-3 py-1.5 text-xs font-semibold text-on-solid shadow-[0_8px_18px_-8px_rgba(36,86,197,0.6)] hover:bg-brand-strong"
          >
            Full reasoning →
          </Link>
        ))}
    </div>
  );
}
