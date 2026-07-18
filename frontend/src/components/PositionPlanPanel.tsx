/** Fixed-risk position sizing over a drawn (or AI-adopted) long/short.
 * Sizing math lives in lib/positionPlan (Constraint 2 mirror); this only
 * renders. Extracted from the Trade workspace so it can live on Portfolio
 * once Trade became chart-only. */
import { useState } from "react";

import { Button } from "./ui/button";
import { useStatus } from "@/lib/api/queries";
import type { Recommendation } from "@/lib/api/types";
import { fmtPrice } from "@/lib/format";
import { computePositionPlan } from "@/lib/positionPlan";
import { useDrawingsStore } from "@/stores/drawings";

const NO_DRAWINGS: never[] = [];

export function PositionPlanPanel({
  symbol,
  rec,
  recPending = false,
  anchorTime,
}: {
  symbol: string;
  rec: Recommendation | null;
  /** ticket query still in flight (R2.7: a slow ticket fetch silently
   * removed the adopt affordance — show a loading state instead) */
  recPending?: boolean;
  /** last bar time — drawing anchors must be EXACT bar times or the
   * chart's timeToCoordinate returns null and nothing renders. null on a
   * chartless page (Portfolio): the drawing seeds the Trade chart, which
   * snaps it to a bar when opened. */
  anchorTime: number | null;
}) {
  const status = useStatus();
  const drawings = useDrawingsStore((s) => s.bySymbol[symbol] ?? NO_DRAWINGS);
  const [riskPct, setRiskPct] = useState("1");
  const position = [...drawings]
    .reverse()
    .find((d) => (d.kind === "long" || d.kind === "short") && d.points.length === 3);

  const adoptAiLevels = () => {
    if (!rec?.entry_price || !rec.stop_loss || !rec.take_profits?.length) return;
    // no chart bar to anchor to (Portfolio): anchor at "now" so the Trade
    // chart snaps it to its latest bar when opened
    const t = anchorTime ?? Math.floor(Date.now() / 1000);
    const side = rec.action === "BUY" ? "long" : "short";
    useDrawingsStore.getState().add(symbol, {
      id: crypto.randomUUID(),
      kind: side,
      points: [
        { time: t, price: rec.entry_price },
        { time: t, price: rec.stop_loss },
        { time: t, price: rec.take_profits[0]!.price },
      ],
    });
  };

  if (!position) {
    return (
      <div className="space-y-2 text-xs text-fg-subtle" data-testid="position-plan">
        <p>
          Draw a position on the chart (long/short tool: entry → stop →
          target) to size it here, or adopt the AI's levels.
        </p>
        {recPending ? (
          <Button size="sm" variant="outline" disabled data-testid="adopt-ai-levels">
            Adopt the AI's levels — loading ticket…
          </Button>
        ) : (
          rec?.entry_price != null &&
          rec.action !== "HOLD" && (
            <Button size="sm" variant="outline" onClick={adoptAiLevels}
                    data-testid="adopt-ai-levels">
              Adopt the AI's levels
            </Button>
          )
        )}
      </div>
    );
  }

  const equity = status.data?.equity ?? null;
  const parsedRisk = Number.parseFloat(riskPct);
  const plan = equity != null
    ? computePositionPlan({
        side: position.kind as "long" | "short",
        entry: position.points[0]!.price,
        stop: position.points[1]!.price,
        target: position.points[2]!.price,
        equity,
        riskPct: Number.isFinite(parsedRisk) ? parsedRisk : 1,
      })
    : null;

  return (
    <div className="space-y-2 text-sm" data-testid="position-plan">
      <p className="font-mono text-xs tabular text-fg-muted">
        {position.kind.toUpperCase()} · entry {fmtPrice(position.points[0]!.price)} ·
        stop {fmtPrice(position.points[1]!.price)} · target {fmtPrice(position.points[2]!.price)}
      </p>
      <label className="flex items-center gap-2 text-xs text-fg-subtle">
        risk % of equity
        <input
          value={riskPct}
          onChange={(e) => setRiskPct(e.target.value)}
          inputMode="decimal"
          className="w-16 rounded-md border border-border bg-surface px-2 py-1 font-mono text-xs tabular"
          data-testid="plan-risk-pct"
        />
      </label>
      {plan == null ? (
        <p className="text-xs text-fg-subtle">equity unavailable (monitor mode)</p>
      ) : !plan.valid ? (
        <p className="text-xs text-bear">{plan.reason}</p>
      ) : (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-xs tabular">
          <dt className="text-fg-subtle">size</dt>
          <dd>{plan.quantity.toFixed(4)}{plan.capped && " (capped)"}</dd>
          <dt className="text-fg-subtle">notional</dt>
          <dd>{fmtPrice(plan.notional, 0)} ({plan.pctOfEquity.toFixed(1)}%)</dd>
          <dt className="text-fg-subtle">risk → reward</dt>
          <dd>
            <span className="text-bear">{fmtPrice(plan.riskAmount, 0)}</span>
            {" → "}
            <span className="text-bull">{fmtPrice(plan.rewardAmount, 0)}</span>
          </dd>
          <dt className="text-fg-subtle">R:R</dt>
          <dd>{plan.rr.toFixed(2)} · breakeven {Math.round(plan.breakevenWinRate * 100)}%</dd>
        </dl>
      )}
      <p className="text-[10px] text-fg-subtle">
        your plan over your levels — not a platform recommendation
      </p>
    </div>
  );
}
