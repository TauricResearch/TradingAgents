/**
 * G1 - Stage-grouped flow map with explicit edges.
 *
 * Six stage containers (analysts → evidence → research → trading → risk →
 * portfolio) hold their role nodes in CSS Grid. An absolutely-positioned
 * inline SVG overlays the entire map and draws edges between measured node
 * geometry via ResizeObserver. Edge kind (handoff / adversarial / convergence)
 * drives stroke treatment.
 *
 * Below a minimum width the map degrades to the stage-grouped grid without
 * edges, avoiding crossing spaghetti on narrow viewports.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useWorkbenchStore } from "../../state/WorkbenchStore";
import { ROLE_REGISTRY } from "../../state/model";
import type { RoleCard } from "../../state/model";
import { EDGES, STAGES } from "../../domain/roles";
import type { EdgeDef } from "../../domain/roles";
import type { StageId, EdgeKind } from "../../domain/roles";
import { RoleCardView } from "./RoleCardView";

interface NodeRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

interface EdgeGeometry {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

const MIN_MAP_WIDTH = 480;

export interface WorkflowMapProps {
  onRoleSelected?: (actor_id: string) => void;
}

export function WorkflowMap({ onRoleSelected }: WorkflowMapProps): JSX.Element {
  const { stream } = useWorkbenchStore();
  const state = stream.state;
  const rolesByActor: Record<string, RoleCard> = state?.roles ?? {};

  const mapRef = useRef<HTMLElement | null>(null);
  const nodeRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [nodeRects, setNodeRects] = useState<Record<string, NodeRect>>({});
  const [mapWidth, setMapWidth] = useState(0);

  // Measure node positions and map width whenever layout changes.
  useEffect(() => {
    const mapEl = mapRef.current;
    if (!mapEl) return;

    const measure = (): void => {
      const mapRect = mapEl.getBoundingClientRect();
      setMapWidth(mapRect.width);
      const rects: Record<string, NodeRect> = {};
      for (const [actor_id, el] of Object.entries(nodeRefs.current)) {
        if (!el) continue;
        const r = el.getBoundingClientRect();
        rects[actor_id] = {
          left: r.left - mapRect.left,
          top: r.top - mapRect.top,
          width: r.width,
          height: r.height,
        };
      }
      setNodeRects(rects);
    };

    measure();

    try {
      const ro = new ResizeObserver(measure);
      ro.observe(mapEl);
      for (const el of Object.values(nodeRefs.current)) {
        if (el) ro.observe(el);
      }
      return () => ro.disconnect();
    } catch {
      // ResizeObserver unavailable (e.g. jsdom); edges render at zero length.
      // The stage grid remains the source of truth for structure.
      return undefined;
    }
  }, []);

  const showEdges = mapWidth >= MIN_MAP_WIDTH;

  const completedCount = useMemo(
    () =>
      ROLE_REGISTRY.filter(
        (def) => rolesByActor[def.actor_id]?.status === "completed",
      ).length,
    [rolesByActor],
  );

  const activeStage = useMemo(() => _deriveActiveStage(rolesByActor), [rolesByActor]);

  const edgePaths = useMemo(() => {
    if (!showEdges) return [];
    return EDGES.map((edge) => ({
      edge,
      geom: _edgeGeometry(edge, nodeRects),
    })).filter((item): item is { edge: EdgeDef; geom: EdgeGeometry } => item.geom !== null);
  }, [nodeRects, showEdges]);

  const setNodeRef = (actor_id: string) => (el: HTMLDivElement | null) => {
    nodeRefs.current[actor_id] = el;
  };

  return (
    <section className="workflow flow-map" ref={mapRef as React.RefObject<HTMLElement>}>
      <div className="section-title">
        <h3>工作流全景</h3>
        <span style={{ fontSize: "10px", color: "var(--muted)" }}>
          {completedCount} / 13 已完成
        </span>
      </div>

      <div className="flow-stages">
        {STAGES.map((stage) => (
          <div
            key={stage.id}
            className={`flow-stage stage-${stage.id} ${
              activeStage === stage.id ? "stage-active" : ""
            }`}
          >
            <div className="stage-label">{stage.title}</div>
            <div className="stage-nodes">
              {stage.actor_ids.map((actor_id) => (
                <div
                  key={actor_id}
                  ref={setNodeRef(actor_id)}
                  data-actor-id={actor_id}
                  className="node-wrapper"
                >
                  <RoleCardView
                    layout={{
                      actor_id,
                      stage: stage.id as StageId,
                      wide: stage.actor_ids.length === 1,
                    }}
                    role={rolesByActor[actor_id] ?? null}
                    onSelected={onRoleSelected}
                  />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {showEdges && edgePaths.length > 0 && (
        <svg
          className="flow-edges"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <defs>
            <marker
              id="arrow-handoff"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--line-2)" />
            </marker>
            <marker
              id="arrow-convergence"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--accent)" />
            </marker>
          </defs>
          {edgePaths.map(({ edge, geom }, i) => {
            const path = _curvedPath(geom, edge.kind);
            return (
              <path
                key={i}
                d={path}
                className={`edge edge-${edge.kind}`}
                fill="none"
                strokeWidth={edge.kind === "adversarial" ? 1.5 : 2}
              />
            );
          })}
        </svg>
      )}
    </section>
  );
}

// --- Geometry helpers ------------------------------------------------------

function _edgeGeometry(
  edge: EdgeDef,
  rects: Record<string, NodeRect>,
): EdgeGeometry | null {
  const from = rects[edge.from];
  const to = rects[edge.to];
  if (!from || !to) return null;

  // Anchor points: center-right of source, center-left of target.
  const x1 = from.left + from.width;
  const y1 = from.top + from.height / 2;
  const x2 = to.left;
  const y2 = to.top + to.height / 2;
  return { x1, y1, x2, y2 };
}

function _curvedPath(geom: EdgeGeometry, kind: EdgeKind): string {
  const { x1, y1, x2, y2 } = geom;
  const dx = x2 - x1;
  const dy = y2 - y1;

  if (kind === "adversarial") {
    // Curved arc between same-stage opponents (more vertical distance).
    const midX = (x1 + x2) / 2;
    const offset = Math.abs(dy) * 0.3 + 10;
    return `M ${x1} ${y1} C ${midX + offset} ${y1}, ${midX - offset} ${y2}, ${x2} ${y2}`;
  }

  // Gentle cubic bezier for handoff and convergence.
  const cpOffset = Math.max(20, dx * 0.4);
  return `M ${x1} ${y1} C ${x1 + cpOffset} ${y1}, ${x2 - cpOffset} ${y2}, ${x2} ${y2}`;
}

function _deriveActiveStage(
  rolesByActor: Record<string, RoleCard>,
): StageId | null {
  // The active stage is the one that has at least one running role, or the
  // latest stage with a completed role if nothing is running.
  const stageOrder: StageId[] = [
    "analysts",
    "evidence",
    "research",
    "trading",
    "risk",
    "portfolio",
  ];
  const actorToStage: Record<string, StageId> = {};
  for (const stage of STAGES) {
    for (const id of stage.actor_ids) {
      actorToStage[id] = stage.id as StageId;
    }
  }

  // Check for running role first.
  for (const [actor_id, role] of Object.entries(rolesByActor)) {
    if (role.status === "running") {
      return actorToStage[actor_id] ?? null;
    }
  }

  // Otherwise, the stage of the latest completed role.
  let latest: StageId | null = null;
  let latestIndex = -1;
  for (const [actor_id, role] of Object.entries(rolesByActor)) {
    if (role.status === "completed") {
      const stage = actorToStage[actor_id];
      const idx = stageOrder.indexOf(stage);
      if (idx > latestIndex) {
        latestIndex = idx;
        latest = stage;
      }
    }
  }
  return latest;
}
