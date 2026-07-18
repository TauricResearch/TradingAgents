/** Right-click actions on the chart (PC.2): set an alert at the clicked
 * price, or explain the nearest AI decision. Anchored at the cursor;
 * Esc / outside-click closes. */
import { useEffect, useRef } from "react";

import { fmtPrice } from "@/lib/format";

export interface ContextTarget {
  x: number;
  y: number;
  price: number | null;
  runId: string | null;
}

export function ChartContextMenu({
  target,
  onClose,
  onAlertHere,
  onExplain,
}: {
  target: ContextTarget;
  onClose: () => void;
  onAlertHere: (price: number) => void;
  onExplain: (runId: string, x: number, y: number) => void;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onDown);
    };
  }, [onClose]);

  return (
    <div
      ref={ref}
      data-testid="chart-context-menu"
      className="absolute z-40 min-w-44 rounded-lg border border-border-strong bg-surface p-1 text-xs shadow-(--shadow-2)"
      style={{ left: Math.max(4, target.x), top: Math.max(4, target.y) }}
    >
      {target.price != null && (
        <button
          className="block w-full rounded px-2 py-1.5 text-left hover:bg-surface-2"
          onClick={() => {
            onAlertHere(target.price!);
            onClose();
          }}
        >
          Alert here · {fmtPrice(target.price)}
        </button>
      )}
      <button
        className="block w-full rounded px-2 py-1.5 text-left hover:bg-surface-2 disabled:opacity-40"
        disabled={!target.runId}
        onClick={() => {
          if (target.runId) onExplain(target.runId, target.x, target.y);
          onClose();
        }}
      >
        {target.runId ? "Explain nearest AI decision" : "No AI decision here"}
      </button>
    </div>
  );
}
