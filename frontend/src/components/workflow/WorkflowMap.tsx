/**
 * G1 - The 3-row, 13-role workflow map.
 *
 * Consumes the workbench store for the live run state and renders all 13
 * role positions as a structural grid. When no run is selected
 * (stream.state === null), every node renders as a pending placeholder so
 * the map is always the product's core structural view (design A).
 *
 * Layout: .workflow > .section-title + 3 × .flow-row > RoleCardView[].
 */
import { useWorkbenchStore } from "../../state/WorkbenchStore";
import { ROLE_REGISTRY } from "../../state/model";
import type { RoleCard } from "../../state/model";
import { ROWS } from "../../domain/roles";
import { RoleCardView } from "./RoleCardView";

export interface WorkflowMapProps {
  onRoleSelected?: (actor_id: string) => void;
}

export function WorkflowMap({ onRoleSelected }: WorkflowMapProps): JSX.Element {
  const { stream } = useWorkbenchStore();
  const state = stream.state;

  // When state is null (no run selected), rolesByActor is empty and every
  // node falls back to the pending placeholder via RoleCardView's role=null.
  const rolesByActor: Record<string, RoleCard> = state?.roles ?? {};
  const completedCount = ROLE_REGISTRY.filter(
    (def) => rolesByActor[def.actor_id]?.status === "completed",
  ).length;

  return (
    <section className="workflow">
      <div className="section-title">
        <h3>工作流全景</h3>
        <span style={{ fontSize: "10px", color: "var(--muted)" }}>
          {completedCount} / 13 已完成
        </span>
      </div>
      {ROWS.map((row, rowIdx) => (
        <div className="flow-row" key={rowIdx}>
          {row.map((layout) => (
            <RoleCardView
              key={layout.actor_id}
              layout={layout}
              role={rolesByActor[layout.actor_id] ?? null}
              onSelected={onRoleSelected}
            />
          ))}
        </div>
      ))}
    </section>
  );
}
