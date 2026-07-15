/** Personalizable module grid over react-grid-layout. Widgets carry
 * their own error boundary + frame; safety chrome lives outside any
 * grid. Drag/resize only in edit mode; mobile renders a fixed
 * priority-ordered stack. */
import { useMemo, useSyncExternalStore } from "react";
import RGL, { WidthProvider, type Layout } from "react-grid-layout";
import { EyeOff, GripVertical } from "lucide-react";

import { ErrorBoundary } from "@/app/ErrorBoundary";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { useLayoutStore, type ModuleId } from "@/stores/layout";
import { cn } from "@/lib/utils";

const Grid = WidthProvider(RGL);

export interface WidgetDef {
  id: string;
  title: string;
  /** card renders its own heading (mockup hero/portfolio) — frame title
   * hidden outside edit mode */
  chromeless?: boolean;
  /** widget's own render already supplies a full-bleed card (bg/border/
   * radius, e.g. the Portfolio Equity gradient panel) — drop the frame's
   * own chrome + padding outside edit mode so it isn't double-boxed */
  bleed?: boolean;
  render: () => React.ReactNode;
  /** grid units; 12-col grid, rowHeight 32 */
  layout: Omit<Layout, "i">;
  headerExtra?: React.ReactNode;
}

// mockup/spec: the grid becomes a priority-ordered stack below 1020px
const STACK_QUERY = "(max-width: 1019px)";

function useIsStacked() {
  return useSyncExternalStore(
    (notify) => {
      const mq = window.matchMedia(STACK_QUERY);
      mq.addEventListener("change", notify);
      return () => mq.removeEventListener("change", notify);
    },
    () => window.matchMedia(STACK_QUERY).matches,
    () => false,
  );
}

export function WidgetGrid({
  module,
  widgets,
}: {
  module: ModuleId;
  widgets: WidgetDef[];
}) {
  const { overrides, editing, saveLayout, showWidget } = useLayoutStore();
  const isStacked = useIsStacked();
  const override = overrides[module];
  const hidden = useMemo(() => new Set(override?.hidden ?? []), [override]);

  const visible = widgets.filter((w) => !hidden.has(w.id));
  const layout: Layout[] = visible.map((w) => {
    const saved = override?.layout.find((l) => l.i === w.id);
    return saved ?? { i: w.id, ...w.layout };
  });

  if (isStacked) {
    // fixed priority stack: definition order, no drag below 1020px
    return (
      <div className="space-y-3 max-md:pb-16">
        {visible.map((w) => (
          <WidgetFrame key={w.id} widget={w} module={module} />
        ))}
      </div>
    );
  }

  return (
    <div>
      {hidden.size > 0 && editing && (
        <div className="mb-2 flex flex-wrap gap-2 text-xs">
          <span className="text-fg-subtle">hidden:</span>
          {[...hidden].map((id) => (
            <button
              key={id}
              className="text-accent hover:underline"
              onClick={() => showWidget(module, id)}
            >
              + {widgets.find((w) => w.id === id)?.title ?? id}
            </button>
          ))}
        </div>
      )}
      <Grid
        className="-mx-2"
        layout={layout}
        cols={12}
        rowHeight={32}
        margin={[12, 12]}
        isDraggable={editing}
        isResizable={editing}
        draggableHandle=".widget-drag-handle"
        onLayoutChange={(next: Layout[]) => {
          if (editing) saveLayout(module, next);
        }}
      >
        {visible.map((w) => (
          <div key={w.id}>
            <WidgetFrame widget={w} module={module} fill />
          </div>
        ))}
      </Grid>
    </div>
  );
}

function WidgetFrame({
  widget,
  module,
  fill = false,
}: {
  widget: WidgetDef;
  module: ModuleId;
  fill?: boolean;
}) {
  const { editing, hideWidget } = useLayoutStore();
  const headerHidden = widget.chromeless && !editing;
  const bleeding = widget.bleed && !editing;
  return (
    <Card
      className={cn(
        fill && "flex h-full flex-col overflow-hidden",
        bleeding && "border-transparent bg-transparent shadow-none backdrop-blur-none",
      )}
    >
      <CardHeader className={cn("shrink-0", headerHidden && "hidden")}>
        <div className="flex items-center gap-1.5">
          {editing && (
            <GripVertical
              size={14}
              className="widget-drag-handle cursor-grab text-fg-subtle"
              aria-label={`drag ${widget.title}`}
            />
          )}
          <CardTitle>{widget.title}</CardTitle>
        </div>
        <div className="flex items-center gap-1">
          {widget.headerExtra}
          {editing && (
            <Button
              size="icon"
              variant="ghost"
              className="h-6 w-6"
              aria-label={`hide ${widget.title}`}
              onClick={() => hideWidget(module, widget.id)}
            >
              <EyeOff size={13} />
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent
        className={cn(
          fill && "min-h-0 grow overflow-y-auto",
          headerHidden && !bleeding && "pt-5",
          bleeding && "p-0",
        )}
      >
        <ErrorBoundary label={widget.title}>{widget.render()}</ErrorBoundary>
      </CardContent>
    </Card>
  );
}
