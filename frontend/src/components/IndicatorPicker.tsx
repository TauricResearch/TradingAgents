/** Indicator selection over the deterministic engine's catalog — the UI
 * offers exactly what /api/bars/indicators computes, nothing else.
 * EMA/SMA/RSI/ATR periods are editable (G7): the id carries the period
 * (EMA_21) so store/query plumbing stays a plain string list. */
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { SlidersHorizontal } from "lucide-react";
import { useState } from "react";

import { Button } from "./ui/button";
import { cn } from "@/lib/utils";

export const INDICATOR_CATALOG = [
  { name: "EMA_10", label: "EMA", overlay: true, family: "EMA", period: 10 },
  { name: "SMA_50", label: "SMA", overlay: true, family: "SMA", period: 50 },
  { name: "SMA_200", label: "SMA 200", overlay: true },
  { name: "BOLL", label: "Bollinger 20/2", overlay: true },
  { name: "VWAP", label: "VWAP (session)", overlay: true, intradayOnly: true },
  { name: "SUPERTREND", label: "Supertrend 14/3", overlay: true },
  { name: "RSI_14", label: "RSI", overlay: false, family: "RSI", period: 14 },
  { name: "MACD", label: "MACD 12/26/9", overlay: false },
  { name: "ATR_14", label: "ATR", overlay: false, family: "ATR", period: 14 },
  { name: "STOCH", label: "Stochastic 9/3", overlay: false },
  { name: "CCI_14", label: "CCI 14", overlay: false },
  { name: "WILLR_14", label: "Williams %R 14", overlay: false },
  { name: "ADX", label: "ADX 14", overlay: false },
  { name: "OBV", label: "OBV", overlay: false },
] as const;

const INTRADAY_TFS = new Set(["1m", "5m", "15m", "30m", "1h", "4h"]);

/** The selected id for a family, e.g. EMA_21 while the catalog default is
 * EMA_10 — one active period per family keeps the pane list readable. */
function selectedFamilyId(selected: string[], family: string): string | null {
  return selected.find((n) => n.startsWith(`${family}_`)) ?? null;
}

export function IndicatorPicker({
  selected,
  onToggle,
  volume,
  onToggleVolume,
  profile,
  onToggleProfile,
  timeframe,
}: {
  selected: string[];
  onToggle: (name: string) => void;
  volume: boolean;
  onToggleVolume: () => void;
  /** volume profile overlay (P2.4); omit to hide the entry */
  profile?: boolean;
  onToggleProfile?: () => void;
  timeframe?: string;
}) {
  const [periods, setPeriods] = useState<Record<string, number>>({});
  const vwapAllowed = timeframe == null || INTRADAY_TFS.has(timeframe);
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button size="sm" variant="outline" data-testid="indicator-picker">
          <SlidersHorizontal size={13} />
          Indicators{selected.length > 0 && ` (${selected.length})`}
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          className="z-50 min-w-48 rounded-md border border-border-strong bg-surface p-1 text-sm shadow-(--shadow-2)"
        >
          <DropdownMenu.CheckboxItem
            checked={volume}
            onCheckedChange={onToggleVolume}
            onSelect={(event) => event.preventDefault()}
            className={cn(
              "cursor-pointer rounded px-2 py-1.5 outline-none data-highlighted:bg-surface-2",
              volume && "text-accent",
            )}
          >
            {volume ? "✓ " : ""}Volume
          </DropdownMenu.CheckboxItem>
          {onToggleProfile && (
            <DropdownMenu.CheckboxItem
              checked={profile}
              onCheckedChange={onToggleProfile}
              onSelect={(event) => event.preventDefault()}
              className={cn(
                "cursor-pointer rounded px-2 py-1.5 outline-none data-highlighted:bg-surface-2",
                profile && "text-accent",
              )}
              data-testid="toggle-volume-profile"
            >
              {profile ? "✓ " : ""}Volume profile
            </DropdownMenu.CheckboxItem>
          )}
          <DropdownMenu.Separator className="my-1 h-px bg-border" />
          {INDICATOR_CATALOG.map((item) => {
            const family = "family" in item ? item.family : null;
            const activeId = family
              ? selectedFamilyId(selected, family)
              : null;
            const effectiveName = activeId ?? item.name;
            const checked = family
              ? activeId != null
              : selected.includes(item.name);
            const defaultPeriod = "period" in item ? item.period : null;
            const period = family
              ? (periods[family] ??
                 (activeId ? Number(activeId.split("_")[1]) : defaultPeriod))
              : null;
            const vwapDisabled = item.name === "VWAP" && !vwapAllowed;
            return (
              <DropdownMenu.CheckboxItem
                key={item.name}
                checked={checked}
                disabled={vwapDisabled}
                onCheckedChange={() => onToggle(effectiveName)}
                onSelect={(event) => event.preventDefault()}
                className={cn(
                  "flex cursor-pointer items-center justify-between gap-2 rounded px-2 py-1.5 outline-none data-highlighted:bg-surface-2",
                  checked && "text-accent",
                  vwapDisabled && "cursor-not-allowed opacity-50",
                )}
                title={vwapDisabled
                  ? "session VWAP needs an intraday timeframe"
                  : undefined}
              >
                <span>
                  {checked ? "✓ " : ""}
                  {item.label}
                </span>
                {family != null ? (
                  <input
                    type="number"
                    min={2}
                    max={400}
                    value={period ?? ""}
                    aria-label={`${family} period`}
                    onClick={(event) => event.stopPropagation()}
                    onKeyDown={(event) => event.stopPropagation()}
                    onChange={(event) => {
                      const next = Number(event.target.value);
                      if (!Number.isFinite(next)) return;
                      setPeriods((prev) => ({ ...prev, [family]: next }));
                      if (activeId != null && next >= 2 && next <= 400) {
                        onToggle(activeId);           // off with old period
                        onToggle(`${family}_${next}`); // on with new period
                      }
                    }}
                    className="w-14 rounded border border-border bg-surface-2 px-1 py-0.5 text-right text-xs tabular"
                  />
                ) : (
                  <span className="text-xs text-fg-subtle">
                    {item.overlay ? "overlay" : "pane"}
                  </span>
                )}
              </DropdownMenu.CheckboxItem>
            );
          })}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
