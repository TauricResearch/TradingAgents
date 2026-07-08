/** Indicator selection over the deterministic engine's catalog — the UI
 * offers exactly what /api/bars/indicators computes, nothing else. */
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, SlidersHorizontal } from "lucide-react";

import { Button } from "./ui/button";
import { cn } from "@/lib/utils";

export const INDICATOR_CATALOG = [
  { name: "EMA_10", label: "EMA 10", overlay: true },
  { name: "SMA_50", label: "SMA 50", overlay: true },
  { name: "SMA_200", label: "SMA 200", overlay: true },
  { name: "BOLL", label: "Bollinger 20/2", overlay: true },
  { name: "RSI_14", label: "RSI 14", overlay: false },
  { name: "MACD", label: "MACD 12/26/9", overlay: false },
  { name: "ATR_14", label: "ATR 14", overlay: false },
] as const;

export function IndicatorPicker({
  selected,
  onToggle,
  volume,
  onToggleVolume,
}: {
  selected: string[];
  onToggle: (name: string) => void;
  volume: boolean;
  onToggleVolume: () => void;
}) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button size="sm" variant="ghost" data-testid="indicator-picker">
          <SlidersHorizontal size={13} />
          Indicators{selected.length > 0 && ` (${selected.length})`}
          <ChevronDown size={12} />
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
          <DropdownMenu.Separator className="my-1 h-px bg-border" />
          {INDICATOR_CATALOG.map((item) => {
            const checked = selected.includes(item.name);
            return (
              <DropdownMenu.CheckboxItem
                key={item.name}
                checked={checked}
                onCheckedChange={() => onToggle(item.name)}
                onSelect={(event) => event.preventDefault()}
                className={cn(
                  "flex cursor-pointer justify-between rounded px-2 py-1.5 outline-none data-highlighted:bg-surface-2",
                  checked && "text-accent",
                )}
              >
                <span>
                  {checked ? "✓ " : ""}
                  {item.label}
                </span>
                <span className="text-xs text-fg-subtle">
                  {item.overlay ? "overlay" : "pane"}
                </span>
              </DropdownMenu.CheckboxItem>
            );
          })}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
