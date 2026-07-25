/**
 * H — compact execution projection for the workbench's live run.
 *
 * Every value comes from the normalized SSE reducer state. In particular, the
 * ETA remains unavailable until completed turns provide real duration samples,
 * and data-source rows are derived from vendor-call provenance rather than a
 * fabricated price-feed/chart contract.
 */
import { ROLE_REGISTRY } from "../../state/model";
import type { CSSProperties } from "react";
import type {
  LogicalToolCall,
  ReducerState,
  RoleCard,
  RoleStatus,
  Turn,
  VendorCall,
} from "../../state/model";
import type { RunStreamStatus } from "../../hooks/useRunStream";
import { ROLE_LABELS_ZH } from "../../domain/roles";
import { ToolProgressIndicator } from "./ToolProgressIndicator";

const TERMINAL_ROLE_STATUSES = new Set([
  "completed",
  "failed",
  "cancelled",
  "interrupted",
  "skipped",
]);

const ACTIVE_TURN_STATUSES = new Set(["started", "resumed"]);

export interface SwarmProgress {
  completed_workers: number;
  settled_workers: number;
  total_workers: number;
  percentage: number;
  active_worker: RoleCard | null;
  active_turn: Turn | null;
  active_tool: LogicalToolCall | null;
  output_ready_count: number;
  elapsed_label: string;
  eta_label: string | null;
  aligned_sources: VendorCall[];
}

function orderedValues<T>(record: Record<string, T>): T[] {
  return Object.values(record);
}

function parseTime(value: string): number | null {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function durationLabel(milliseconds: number): string {
  const seconds = Math.max(0, Math.round(milliseconds / 1000));
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function findActiveTurn(state: ReducerState): Turn | null {
  const turns = orderedValues(state.turns);
  for (let index = turns.length - 1; index >= 0; index -= 1) {
    if (ACTIVE_TURN_STATUSES.has(turns[index].status)) return turns[index];
  }
  return null;
}

function findActiveTool(state: ReducerState): LogicalToolCall | null {
  const calls = orderedValues(state.tool_calls);
  for (let index = calls.length - 1; index >= 0; index -= 1) {
    const call = calls[index];
    if (call.status === "requested" || call.status === "running") return call;
  }
  return null;
}

function findAlignedSources(
  state: ReducerState,
  activeTurn: Turn | null,
): VendorCall[] {
  const calls = orderedValues(state.vendor_calls);
  const relevant = activeTurn
    ? calls.filter((call) => call.turn_id === activeTurn.turn_id)
    : calls.filter((call) => call.status === "progress");
  // The latest event for each source has already overwritten the same
  // vendor_call_id in the reducer, so these are live provenance rows.
  return relevant.slice(-3).reverse();
}

export function deriveSwarmProgress(state: ReducerState): SwarmProgress {
  const roles = ROLE_REGISTRY.map((definition) => state.roles[definition.actor_id]);
  const completed_workers = roles.filter((role) => role?.status === "completed").length;
  const settled_workers = roles.filter(
    (role) => role && TERMINAL_ROLE_STATUSES.has(role.status),
  ).length;
  const active_worker =
    roles.find((role) => role?.status === "running") ?? null;
  const active_turn = findActiveTurn(state);
  const active_tool = findActiveTool(state);
  const output_ready_count = orderedValues(state.turns).filter(
    (turn) => turn.status === "output_ready",
  ).length;
  const start = parseTime(state.meta.created_at);
  const lastUpdate = parseTime(state.meta.updated_at);
  const elapsed_label =
    start !== null && lastUpdate !== null && lastUpdate >= start
      ? durationLabel(lastUpdate - start)
      : "—";
  const completedDurations = orderedValues(state.turns)
    .filter((turn) => turn.status === "completed" && turn.duration_ms !== undefined)
    .map((turn) => turn.duration_ms as number);
  const averageDuration =
    completedDurations.length > 0
      ? completedDurations.reduce((sum, duration) => sum + duration, 0) /
        completedDurations.length
      : null;
  const remaining = ROLE_REGISTRY.length - settled_workers;
  const eta_label =
    averageDuration !== null && remaining > 0 && state.meta.status === "running"
      ? `参考余量 ${durationLabel(averageDuration * remaining)}`
      : null;

  return {
    completed_workers,
    settled_workers,
    total_workers: ROLE_REGISTRY.length,
    percentage: Math.round((settled_workers / ROLE_REGISTRY.length) * 100),
    active_worker,
    active_turn,
    active_tool,
    output_ready_count,
    elapsed_label,
    eta_label,
    aligned_sources: findAlignedSources(state, active_turn),
  };
}

const ROLE_STATUS_LABELS: Record<RoleStatus, string> = {
  pending: "等待",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
  skipped: "已跳过",
  not_reached: "未到达",
};

export interface WorkerRow {
  actor_id: string;
  label: string;
  status: RoleStatus;
  tool_name: string | null;
  duration_label: string;
  round_label: string | null;
}

function latestTurnForRole(state: ReducerState, actor_id: string): Turn | null {
  let latest: Turn | null = null;
  for (const turn of orderedValues(state.turns)) {
    if (turn.actor_id !== actor_id) continue;
    if (latest === null || turn.turn_index > latest.turn_index) latest = turn;
  }
  return latest;
}

function activeToolForTurn(
  state: ReducerState,
  turn: Turn,
): LogicalToolCall | null {
  for (const id of turn.tool_call_ids) {
    const call = state.tool_calls[id];
    if (call && (call.status === "requested" || call.status === "running")) {
      return call;
    }
  }
  return null;
}

function latestCompletedTurnForRole(
  state: ReducerState,
  actor_id: string,
): Turn | null {
  // Duration is only meaningful once a turn has actually finished; an
  // output_ready or started turn has no duration yet, so we read the most
  // recent completed turn for this role rather than the latest turn overall.
  let latest: Turn | null = null;
  for (const turn of orderedValues(state.turns)) {
    if (turn.actor_id !== actor_id || turn.status !== "completed") continue;
    if (latest === null || turn.turn_index > latest.turn_index) latest = turn;
  }
  return latest;
}

export function deriveWorkerRows(state: ReducerState): WorkerRow[] {
  // One row per registered role, sourced only from persisted reducer state.
  // Roles never reached in this run are shown as "未到达" rather than omitted,
  // so the table is a stable 13-row execution map.
  return ROLE_REGISTRY.map((definition) => {
    const role = state.roles[definition.actor_id];
    const status: RoleStatus = role?.status ?? "not_reached";
    const turn = latestTurnForRole(state, definition.actor_id);
    const completedTurn = latestCompletedTurnForRole(state, definition.actor_id);
    const tool = turn ? activeToolForTurn(state, turn) : null;
    const round = role?.current_round ?? turn?.turn_index;
    return {
      actor_id: definition.actor_id,
      label: ROLE_LABELS_ZH[definition.actor_id] ?? definition.display_name,
      status,
      tool_name: tool?.tool_name ?? null,
      duration_label:
        completedTurn?.duration_ms !== undefined
          ? durationLabel(completedTurn.duration_ms)
          : "-",
      round_label: round !== undefined ? `第 ${round} 轮` : null,
    };
  });
}

function roleLabel(role: RoleCard | null, activeTurn: Turn | null): string {
  if (role) return ROLE_LABELS_ZH[role.actor_id] ?? role.actor_id;
  if (activeTurn) return ROLE_LABELS_ZH[activeTurn.actor_id] ?? activeTurn.actor_id;
  return "等待下一个角色";
}

function sourceStatusLabel(source: VendorCall): string {
  switch (source.status) {
    case "completed":
      return "已同步";
    case "failed":
      return "失败";
    case "interrupted":
      return "已中断";
    default:
      return "同步中";
  }
}

export interface SwarmStatusCardProps {
  state: ReducerState;
  streamStatus: RunStreamStatus;
}

export function SwarmStatusCard({
  state,
  streamStatus,
}: SwarmStatusCardProps): JSX.Element {
  const progress = deriveSwarmProgress(state);
  const workerRows = deriveWorkerRows(state);
  const activeLabel = roleLabel(progress.active_worker, progress.active_turn);
  const turnIndex = progress.active_turn?.turn_index ?? progress.active_worker?.current_round;
  const ringStyle = { "--swarm-progress": `${progress.percentage * 3.6}deg` } as CSSProperties;

  return (
    <section className="swarm-status" aria-label="执行状态">
      <div className="swarm-status-head">
        <div>
          <span className="eyebrow">Swarm status</span>
          <h3>{activeLabel}</h3>
        </div>
        <div
          className="swarm-progress-ring"
          style={ringStyle}
          role="img"
          aria-label={`链路推进 ${progress.percentage}%`}
        >
          <strong>{progress.percentage}%</strong>
          <span>推进</span>
        </div>
      </div>

      {state.meta.status === "failed" && state.meta.error_message && (
        <div className="swarm-error" role="alert">
          <span className="eyebrow">失败原因</span>
          <div className="swarm-error-category">
            {state.meta.error_category ?? "unexpected_internal_failure"}
          </div>
          <code className="swarm-error-message">{state.meta.error_message}</code>
        </div>
      )}

      <div className="swarm-metrics">
        <div>
          <span>工作角色</span>
          <strong>{progress.completed_workers} / {progress.total_workers} 已完成</strong>
        </div>
        <div>
          <span>产出候选</span>
          <strong>{progress.output_ready_count} 已就绪</strong>
        </div>
        <div>
          <span>已观察</span>
          <strong>{progress.elapsed_label}</strong>
        </div>
      </div>

      <div className="swarm-workers" aria-label="逐角色状态">
        <span className="eyebrow">逐角色状态</span>
        <table className="swarm-workers-table">
          <thead>
            <tr>
              <th scope="col">角色</th>
              <th scope="col">状态</th>
              <th scope="col">当前工具</th>
              <th scope="col">耗时</th>
              <th scope="col">轮次</th>
            </tr>
          </thead>
          <tbody>
            {workerRows.map((row) => (
              <tr key={row.actor_id} className={`worker-row worker-status-${row.status}`}>
                <th scope="row">{row.label}</th>
                <td>{ROLE_STATUS_LABELS[row.status] ?? row.status}</td>
                <td>{row.tool_name ?? "-"}</td>
                <td>{row.duration_label}</td>
                <td>{row.round_label ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="swarm-current">
        <span className={streamStatus === "live" ? "live-pulse" : ""} aria-hidden="true" />
        <span>{streamStatus === "live" ? "事件流已连接" : `事件流：${streamStatus}`}</span>
        {turnIndex !== undefined && <span>第 {turnIndex} 轮</span>}
        {progress.eta_label && <span>{progress.eta_label}</span>}
      </div>

      <ToolProgressIndicator tool={progress.active_tool} />

      <div className="source-alignment">
        <span className="eyebrow">数据源对齐</span>
        {progress.aligned_sources.length === 0 ? (
          <span className="source-alignment-empty">尚无可对应的数据源事件</span>
        ) : (
          <ul>
            {progress.aligned_sources.map((source) => (
              <li key={source.vendor_call_id}>
                <span className={`source-status source-status-${source.status}`} aria-hidden="true" />
                <strong>{source.vendor}</strong>
                <span>{source.method}</span>
                <span>{source.stage}</span>
                <span>{sourceStatusLabel(source)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
