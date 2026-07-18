/** Drawing tool selector, clubbed into TradingView-style groups: related
 * tools share one rail button (showing the group's current tool) with a
 * corner caret that opens a flyout to switch within the group. Keeps every
 * tool while roughly halving the rail. Desktop-only (touch drawing is out
 * of scope and we say so rather than ship a bad version). */
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useState } from "react";
import {
  AlignEndHorizontal,
  ArrowDownRight,
  ArrowUpRight,
  Bell,
  Eraser,
  Eye,
  EyeOff,
  List,
  Magnet,
  Minus,
  MousePointer2,
  MoveUpRight,
  MoveVertical,
  Redo2,
  Rows3,
  Ruler,
  Square,
  Trash2,
  TrendingUp,
  Type,
  Undo2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { Drawing, ToolMode } from "./types";

type Tool = { mode: ToolMode; icon: typeof MousePointer2; label: string };
type Group = { name: string; tools: Tool[] };

const T = {
  select: { mode: "select", icon: MousePointer2, label: "Select / pan" },
  trend: { mode: "trend", icon: TrendingUp, label: "Trendline (2 clicks)" },
  hray: { mode: "hray", icon: Minus, label: "Horizontal ray (1 click)" },
  vline: { mode: "vline", icon: MoveVertical, label: "Vertical line (1 click)" },
  arrow: { mode: "arrow", icon: MoveUpRight, label: "Arrow (2 clicks)" },
  fib: { mode: "fib", icon: AlignEndHorizontal, label: "Fib retracement (2 clicks)" },
  long: { mode: "long", icon: ArrowUpRight, label: "Long position (entry → stop → target)" },
  short: { mode: "short", icon: ArrowDownRight, label: "Short position (entry → stop → target)" },
  rect: { mode: "rect", icon: Square, label: "Zone / rectangle (2 clicks)" },
  channel: { mode: "channel", icon: Rows3, label: "Parallel channel (base line, then offset)" },
  text: { mode: "text", icon: Type, label: "Text note (1 click)" },
  alert: { mode: "alert", icon: Bell, label: "Price alert (click a level)" },
  measure: { mode: "measure", icon: Ruler, label: "Measure (2 clicks; Esc clears)" },
  erase: { mode: "erase", icon: Eraser, label: "Erase (click a drawing)" },
} satisfies Record<string, Tool>;

// clubbed like a pro terminal: line tools together, position tools
// together, shapes/notes together; cursor / fib / measure / alert / erase
// stay single. Each multi-tool group opens a flyout via its corner caret.
const GROUPS: Group[] = [
  { name: "Cursor", tools: [T.select] },
  { name: "Lines", tools: [T.trend, T.hray, T.vline, T.arrow, T.channel] },
  { name: "Fibonacci", tools: [T.fib] },
  { name: "Positions", tools: [T.long, T.short] },
  { name: "Shapes & notes", tools: [T.rect, T.text] },
  { name: "Measure", tools: [T.measure] },
  { name: "Alerts", tools: [T.alert] },
  { name: "Eraser", tools: [T.erase] },
];

/** One rail slot: a main button that activates the group's current tool,
 * plus (for multi-tool groups) a corner caret opening a flyout to switch. */
function ToolGroup({
  group,
  mode,
  remembered,
  onActivate,
}: {
  group: Group;
  mode: ToolMode;
  remembered: ToolMode;
  onActivate: (mode: ToolMode) => void;
}) {
  const active = group.tools.find((t) => t.mode === mode) ?? null;
  const shown =
    group.tools.find((t) => t.mode === (active?.mode ?? remembered)) ??
    group.tools[0]!;
  const multi = group.tools.length > 1;
  return (
    <div className="relative">
      <Tip content={multi ? `${group.name} · ${shown.label}` : shown.label}>
        <Button
          size="icon"
          variant="ghost"
          aria-label={shown.label}
          aria-pressed={active != null}
          className={cn(
            "h-[30px] w-[30px] rounded-[9px] border border-border",
            active != null && "bg-accent-muted text-accent",
          )}
          onClick={() => onActivate(shown.mode)}
        >
          <shown.icon size={13} />
        </Button>
      </Tip>
      {multi && (
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              aria-label={`${group.name} tools`}
              className="absolute -bottom-px -right-px flex size-3 items-center justify-center rounded-[4px] text-fg-subtle hover:text-fg"
            >
              <span className="text-[7px] leading-none">◢</span>
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              side="right"
              align="start"
              sideOffset={6}
              className="z-50 min-w-48 rounded-md border border-border-strong bg-surface p-1 text-xs shadow-(--shadow-2)"
            >
              <DropdownMenu.Label className="px-2 py-1 text-[10px] uppercase tracking-wide text-fg-subtle">
                {group.name}
              </DropdownMenu.Label>
              {group.tools.map((t) => (
                <DropdownMenu.Item
                  key={t.mode}
                  aria-label={t.label}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 outline-none data-[highlighted]:bg-surface-2",
                    mode === t.mode && "text-accent",
                  )}
                  onSelect={() => onActivate(t.mode)}
                >
                  <t.icon size={13} /> {t.label}
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      )}
    </div>
  );
}

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
  magnet = false,
  onMagnetChange,
  onUndo,
  onRedo,
  canUndo = false,
  canRedo = false,
}: {
  mode: ToolMode;
  onModeChange: (mode: ToolMode) => void;
  drawings: Drawing[];
  onClearAll: () => void;
  onToggleHidden: (id: string) => void;
  onRemove: (id: string) => void;
  /** snap drawing anchors to the clicked bar's O/H/L/C */
  magnet?: boolean;
  onMagnetChange?: (on: boolean) => void;
  onUndo?: () => void;
  onRedo?: () => void;
  canUndo?: boolean;
  canRedo?: boolean;
}) {
  const count = drawings.length;
  // per-group "current tool" memory so a group button re-activates the last
  // tool picked from its flyout (defaults to the group's first tool).
  const [remembered, setRemembered] = useState<Record<string, ToolMode>>({});
  const activate = (group: Group, m: ToolMode) => {
    onModeChange(m);
    setRemembered((r) => ({ ...r, [group.name]: m }));
  };
  return (
    <div
      className="flex flex-col items-center gap-1 pt-1 max-md:hidden"
      role="toolbar"
      aria-label="Drawing tools"
      data-testid="drawing-toolbar"
    >
      {GROUPS.map((group) => (
        <ToolGroup
          key={group.name}
          group={group}
          mode={mode}
          remembered={remembered[group.name] ?? group.tools[0]!.mode}
          onActivate={(m) => activate(group, m)}
        />
      ))}
      {onUndo && (
        <Tip content="Undo (⌘Z)">
          <Button
            size="icon"
            variant="ghost"
            aria-label="Undo drawing"
            disabled={!canUndo}
            className="h-[30px] w-[30px] rounded-[9px] border border-border"
            onClick={onUndo}
          >
            <Undo2 size={13} />
          </Button>
        </Tip>
      )}
      {onRedo && (
        <Tip content="Redo (⇧⌘Z)">
          <Button
            size="icon"
            variant="ghost"
            aria-label="Redo drawing"
            disabled={!canRedo}
            className="h-[30px] w-[30px] rounded-[9px] border border-border"
            onClick={onRedo}
          >
            <Redo2 size={13} />
          </Button>
        </Tip>
      )}
      {onMagnetChange && (
        <Tip content={magnet ? "Magnet on: anchors snap to O/H/L/C" : "Magnet off"}>
          <Button
            size="icon"
            variant="ghost"
            aria-label="Magnet mode (snap to OHLC)"
            aria-pressed={magnet}
            className={cn(
              "h-[30px] w-[30px] rounded-[9px] border border-border",
              magnet && "bg-accent-muted text-accent",
            )}
            onClick={() => onMagnetChange(!magnet)}
          >
            <Magnet size={13} />
          </Button>
        </Tip>
      )}
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
