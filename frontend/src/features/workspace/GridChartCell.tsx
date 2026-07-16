/** One cell of the multi-chart grid (review P2.6): its own symbol and
 * timeframe, crosshair-synced with the main chart through the workspace
 * sync group. Deliberately lean — candles + volume only; the full
 * toolkit (drawings, indicators, replay) lives on the main chart. */
import { PriceChart } from "@/components/charts/PriceChart";
import { SkeletonCard } from "@/components/ui/skeleton";
import { useBars, useSymbols } from "@/lib/api/queries";
import type { GridCell } from "@/stores/ui";

export function GridChartCell({
  cell,
  onChange,
  syncId,
}: {
  cell: GridCell;
  onChange: (next: Partial<GridCell>) => void;
  syncId: string;
}) {
  const symbols = useSymbols();
  const spec = symbols.data?.find((s) => s.symbol === cell.symbol);
  const timeframes = spec?.timeframes ?? ["1d"];
  const activeTf = timeframes.includes(cell.timeframe)
    ? cell.timeframe
    : timeframes[timeframes.length - 1]!;
  const bars = useBars(cell.symbol, activeTf, 300);

  return (
    <div
      className="rounded-xl border border-border p-2"
      data-testid="grid-chart-cell"
    >
      <div className="mb-1 flex items-center gap-2 text-xs">
        <select
          value={cell.symbol}
          onChange={(e) => onChange({ symbol: e.target.value })}
          className="rounded-md border border-border bg-surface px-1.5 py-0.5 font-mono font-bold"
          aria-label="Grid cell symbol"
        >
          {(symbols.data ?? []).map((s) => (
            <option key={s.symbol} value={s.symbol}>
              {s.symbol}
            </option>
          ))}
        </select>
        <select
          value={activeTf}
          onChange={(e) => onChange({ timeframe: e.target.value })}
          className="rounded-md border border-border bg-surface px-1.5 py-0.5 font-mono"
          aria-label="Grid cell timeframe"
        >
          {timeframes.map((tf) => (
            <option key={tf} value={tf}>
              {tf}
            </option>
          ))}
        </select>
      </div>
      {bars.data ? (
        <PriceChart
          bars={bars.data}
          style="candles"
          liveSymbol={cell.symbol}
          showVolume
          syncId={syncId}
          height={210}
        />
      ) : (
        <SkeletonCard lines={4} />
      )}
    </div>
  );
}
