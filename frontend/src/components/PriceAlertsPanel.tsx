/** Notify-only user price alerts (G4) with one-click presets from the
 * current ticket's own levels — set an alert on the AI's invalidation
 * price in one tap. Extracted from the Trade workspace so it can live on
 * Portfolio once Trade became chart-only. */
import { useState } from "react";

import { Button } from "./ui/button";
import { useQueryClient } from "@tanstack/react-query";

import {
  createPriceAlert,
  deletePriceAlert,
  usePriceAlerts,
} from "@/lib/api/queries";
import type { Recommendation } from "@/lib/api/types";
import { fmtPrice } from "@/lib/format";

export function PriceAlertsPanel({
  symbol,
  rec,
}: {
  symbol: string;
  rec: Recommendation | null;
}) {
  const client = useQueryClient();
  const alerts = usePriceAlerts();
  const [level, setLevel] = useState("");
  const [direction, setDirection] = useState<"above" | "below">("above");
  const [error, setError] = useState<string | null>(null);

  const mine = (alerts.data ?? []).filter(
    (a) => a.symbol === symbol && a.active,
  );
  const presets = rec
    ? ([
        ["ENTRY", rec.entry_price],
        ["STOP", rec.stop_loss],
        ["TP1", rec.take_profits?.[0]?.price],
      ] as const).filter(([, price]) => price != null)
    : [];

  const submit = async (lvl: number, dir: "above" | "below", note = "") => {
    setError(null);
    try {
      await createPriceAlert(client, { symbol, level: lvl, direction: dir, note });
      setLevel("");
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div className="space-y-2 text-sm" data-testid="price-alerts">
      {mine.length === 0 ? (
        <p className="text-xs text-fg-subtle">
          No alerts for {symbol}. Alerts notify (bell, Telegram when
          configured) — they never trade.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {mine.map((alert) => (
            <li
              key={alert.id}
              className="flex items-center justify-between gap-2 rounded-[12px] bg-surface-2 px-3 py-[7px] text-[12.5px]"
            >
              <span className="font-mono font-bold tabular">
                {alert.direction === "above" ? "≥" : "≤"} {fmtPrice(alert.level)}
              </span>
              <span className="grow truncate text-xs text-fg-subtle">
                {alert.note}
              </span>
              <button
                onClick={() => void deletePriceAlert(client, alert.id)}
                aria-label={`Delete alert at ${alert.level}`}
                className="flex size-[22px] shrink-0 items-center justify-center rounded-[7px] text-fg-subtle hover:bg-bear-muted hover:text-bear"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      <form
        className="flex items-center gap-1.5"
        onSubmit={(event) => {
          event.preventDefault();
          const lvl = Number(level);
          if (Number.isFinite(lvl) && lvl > 0) void submit(lvl, direction);
        }}
      >
        <input
          type="number"
          step="any"
          min="0"
          placeholder="price level"
          value={level}
          onChange={(event) => setLevel(event.target.value)}
          aria-label="Alert price level"
          data-testid="price-alert-level"
          className="w-24 rounded-lg border border-border bg-surface-2 px-2 py-1 text-xs tabular outline-none focus:border-accent"
        />
        <button
          type="button"
          onClick={() => setDirection(direction === "above" ? "below" : "above")}
          aria-label="Toggle direction"
          className="rounded-lg border border-border px-2 py-1 text-xs font-semibold"
        >
          {direction === "above" ? "↑ above" : "↓ below"}
        </button>
        <Button size="sm" type="submit" data-testid="price-alert-create">
          Alert
        </Button>
      </form>
      {presets.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {presets.map(([label, price]) => (
            <button
              key={label}
              onClick={() =>
                void submit(
                  price!,
                  rec && rec.entry_price != null && price! >= rec.entry_price
                    ? "above"
                    : "below",
                  `${label} from run ${rec?.id ?? ""}`.trim(),
                )
              }
              className="rounded-full border border-accent/40 bg-accent-muted px-2 py-0.5 text-[11px] font-semibold text-accent"
            >
              alert @ {label} {fmtPrice(price)}
            </button>
          ))}
        </div>
      )}
      {error && <p className="text-xs text-bear">{error}</p>}
    </div>
  );
}
