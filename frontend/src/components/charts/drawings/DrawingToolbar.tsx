/** Drawing tool selector: select / trendline / horizontal ray / fib /
 * eraser / clear-all. Desktop-only (touch drawing is out of scope and
 * we say so rather than ship a bad version). */
import {
  Eraser,
  Minus,
  MousePointer2,
  TrendingUp,
  Trash2,
  AlignEndHorizontal,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { ToolMode } from "./types";

const TOOLS: { mode: ToolMode; icon: typeof MousePointer2; label: string }[] = [
  { mode: "select", icon: MousePointer2, label: "Select / pan" },
  { mode: "trend", icon: TrendingUp, label: "Trendline (2 clicks)" },
  { mode: "hray", icon: Minus, label: "Horizontal ray (1 click)" },
  { mode: "fib", icon: AlignEndHorizontal, label: "Fib retracement (2 clicks)" },
  { mode: "erase", icon: Eraser, label: "Erase (click a drawing)" },
];

export function DrawingToolbar({
  mode,
  onModeChange,
  count,
  onClearAll,
}: {
  mode: ToolMode;
  onModeChange: (mode: ToolMode) => void;
  count: number;
  onClearAll: () => void;
}) {
  return (
    <div
      className="flex flex-col gap-0.5 rounded-md border border-border bg-surface-2/60 p-0.5 max-md:hidden"
      role="toolbar"
      aria-label="Drawing tools"
      data-testid="drawing-toolbar"
    >
      {TOOLS.map((tool) => (
        <Tip key={tool.mode} content={tool.label}>
          <Button
            size="icon"
            variant="ghost"
            aria-label={tool.label}
            aria-pressed={mode === tool.mode}
            className={cn(
              "h-7 w-7",
              mode === tool.mode && "bg-accent-muted text-accent",
            )}
            onClick={() => onModeChange(tool.mode)}
          >
            <tool.icon size={14} />
          </Button>
        </Tip>
      ))}
      <Tip content={`Clear all drawings for this symbol (${count})`}>
        <Button
          size="icon"
          variant="ghost"
          aria-label={`Clear all drawings (${count})`}
          className="h-7 w-7 text-bear/70 hover:text-bear"
          disabled={count === 0}
          onClick={onClearAll}
        >
          <Trash2 size={14} />
        </Button>
      </Tip>
    </div>
  );
}
