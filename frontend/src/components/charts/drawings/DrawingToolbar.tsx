/** Drawing tool selector: select / trendline / horizontal ray / fib /
 * eraser / clear-all. Desktop-only (touch drawing is out of scope and
 * we say so rather than ship a bad version). */
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  AlignEndHorizontal,
  ArrowDownRight,
  ArrowUpRight,
  Bell,
  Eraser,
  Eye,
  EyeOff,
  List,
  Minus,
  MousePointer2,
  Rows3,
  Square,
  Trash2,
  TrendingUp,
  Type,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { Drawing, ToolMode } from "./types";

const TOOLS: { mode: ToolMode; icon: typeof MousePointer2; label: string }[] = [
  { mode: "select", icon: MousePointer2, label: "Select / pan" },
  { mode: "trend", icon: TrendingUp, label: "Trendline (2 clicks)" },
  { mode: "hray", icon: Minus, label: "Horizontal ray (1 click)" },
  { mode: "fib", icon: AlignEndHorizontal, label: "Fib retracement (2 clicks)" },
  { mode: "long", icon: ArrowUpRight, label: "Long position (entry → stop → target)" },
  { mode: "short", icon: ArrowDownRight, label: "Short position (entry → stop → target)" },
  { mode: "rect", icon: Square, label: "Zone / rectangle (2 clicks)" },
  { mode: "channel", icon: Rows3, label: "Parallel channel (base line, then offset)" },
  { mode: "text", icon: Type, label: "Text note (1 click)" },
  { mode: "alert", icon: Bell, label: "Price alert (click a level)" },
  { mode: "erase", icon: Eraser, label: "Erase (click a drawing)" },
];

/** One line per drawing for the object list: kind + anchor price(s). */
function describeDrawing(drawing: Drawing): string {
  const price = drawing.points[0]?.price;
  if (drawing.kind === "text") return `note “${drawing.text ?? "…"}”`;
  if (drawing.kind === "long" || drawing.kind === "short")
    return `${drawing.kind} @ ${price?.toFixed(2) ?? "?"}`;
  return `${drawing.kind} @ ${price?.toFixed(2) ?? "?"}`;
}

export function DrawingToolbar({
  mode,
  onModeChange,
  drawings,
  onClearAll,
  onToggleHidden,
  onRemove,
}: {
  mode: ToolMode;
  onModeChange: (mode: ToolMode) => void;
  drawings: Drawing[];
  onClearAll: () => void;
  onToggleHidden: (id: string) => void;
  onRemove: (id: string) => void;
}) {
  const count = drawings.length;
  return (
    <div
      className="flex flex-col items-center gap-1 pt-1 max-md:hidden"
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
              "h-[30px] w-[30px] rounded-[9px] border border-border",
              mode === tool.mode && "bg-accent-muted text-accent",
            )}
            onClick={() => onModeChange(tool.mode)}
          >
            <tool.icon size={13} />
          </Button>
        </Tip>
      ))}
      {/* object list (review P2.2): every drawing, hide/show + delete —
          hiding is reversible, deleting is not, both one click away */}
      <DropdownMenu.Root>
        <Tip content={`Objects (${count})`}>
          <DropdownMenu.Trigger asChild>
            <Button
              size="icon"
              variant="ghost"
              aria-label={`Objects (${count})`}
              disabled={count === 0}
              className="h-[30px] w-[30px] rounded-[9px] border border-border"
              data-testid="object-list-trigger"
            >
              <List size={13} />
            </Button>
          </DropdownMenu.Trigger>
        </Tip>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            side="right"
            align="start"
            className="z-50 min-w-52 rounded-md border border-border-strong bg-surface p-1 text-xs shadow-(--shadow-2)"
            data-testid="object-list"
          >
            {drawings.map((drawing) => (
              <div
                key={drawing.id}
                className={cn(
                  "flex items-center justify-between gap-2 rounded px-2 py-1",
                  drawing.hidden && "opacity-50",
                )}
              >
                <span className="font-mono">{describeDrawing(drawing)}</span>
                <span className="flex shrink-0 gap-1">
                  <button
                    aria-label={drawing.hidden ? "Show" : "Hide"}
                    className="rounded p-0.5 hover:bg-surface-2"
                    onClick={() => onToggleHidden(drawing.id)}
                  >
                    {drawing.hidden ? <EyeOff size={12} /> : <Eye size={12} />}
                  </button>
                  <button
                    aria-label="Delete drawing"
                    className="rounded p-0.5 text-bear/70 hover:bg-surface-2 hover:text-bear"
                    onClick={() => onRemove(drawing.id)}
                  >
                    <Trash2 size={12} />
                  </button>
                </span>
              </div>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      <Tip content={`Clear all drawings for this symbol (${count})`}>
        <Button
          size="icon"
          variant="ghost"
          aria-label={`Clear all drawings (${count})`}
          className="h-[30px] w-[30px] rounded-[9px] border border-border text-bear/70 hover:text-bear"
          disabled={count === 0}
          onClick={onClearAll}
        >
          <Trash2 size={13} />
        </Button>
      </Tip>
    </div>
  );
}
