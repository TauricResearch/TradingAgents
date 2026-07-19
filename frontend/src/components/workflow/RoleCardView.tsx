/**
 * G1 - One role node in the 13-role workflow map.
 *
 * Renders the role's icon (via RoleIcon), Chinese display name, and a status
 * line driven by RoleCard.status (or statusOverride). When role is null (no
 * run selected / role not yet present in state), renders a pending placeholder
 * so the workflow map always shows all 13 structural positions (design A).
 *
 * CSS classes from workbench.css: .node, .node.done, .node.live, .node.bull,
 * .node.bear, .node.risk, .node.wide, .node-icon, .node-name, .node-status.
 */
import { RoleIcon } from "../icons/RoleIcon";
import { ROLE_REGISTRY } from "../../state/model";
import type { RoleCard, RoleStatus } from "../../state/model";
import { ROLE_LABELS_ZH, stageColorClass } from "../../domain/roles";
import type { RoleLayoutEntry } from "../../domain/roles";

export interface RoleCardViewProps {
  role: RoleCard | null;
  layout: RoleLayoutEntry;
  /** Overrides role.status when set (used by callers to force a display state). */
  statusOverride?: RoleStatus;
  /** Invoked with the actor_id on click, when provided. */
  onSelected?: (actor_id: string) => void;
}

/** Resolve icon_id from ROLE_REGISTRY by actor_id (13-entry linear scan). */
function iconIdFor(actor_id: string): string {
  for (const def of ROLE_REGISTRY) {
    if (def.actor_id === actor_id) return def.icon_id;
  }
  return "";
}

function renderStatusLine(status: RoleStatus, round: number): JSX.Element {
  switch (status) {
    case "pending":
      return <div className="node-status">待运行</div>;
    case "running":
      return (
        <div className="node-status">
          ● 运行中{round > 0 ? ` · 第 ${round} 轮` : ""}
        </div>
      );
    case "completed":
      return <div className="node-status">✓ 已完成</div>;
    case "failed":
      return (
        <div className="node-status" style={{ color: "var(--red)" }}>
          ✗ 失败
        </div>
      );
    case "cancelled":
      return <div className="node-status">已取消</div>;
    case "interrupted":
      return (
        <div className="node-status" style={{ color: "var(--gold)" }}>
          已中断
        </div>
      );
    case "skipped":
      return (
        <div className="node-status" style={{ fontStyle: "italic" }}>
          未选择
        </div>
      );
    case "not_reached":
      return <div className="node-status">未到达</div>;
  }
}

export function RoleCardView({
  role,
  layout,
  statusOverride,
  onSelected,
}: RoleCardViewProps): JSX.Element {
  const actor_id = layout.actor_id;
  const status: RoleStatus = statusOverride ?? role?.status ?? "pending";
  const label = ROLE_LABELS_ZH[actor_id] ?? actor_id;
  const icon_id = iconIdFor(actor_id);
  const colorClass = stageColorClass(actor_id);
  const round = role?.current_round ?? 0;

  const classNames = ["node"];
  if (colorClass) classNames.push(colorClass);
  if (layout.wide) classNames.push("wide");
  if (status === "completed") classNames.push("done");
  if (status === "running") classNames.push("live");

  return (
    <div
      className={classNames.join(" ")}
      data-actor-id={actor_id}
      onClick={onSelected ? () => onSelected(actor_id) : undefined}
    >
      <RoleIcon icon_id={icon_id} size={22} className="node-icon" />
      <div className="node-name">{label}</div>
      {renderStatusLine(status, round)}
    </div>
  );
}
