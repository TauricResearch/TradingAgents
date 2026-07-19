/**
 * G3 - Tool call card for the 数据与工具 inspector tab.
 *
 * Renders a single LogicalToolCall with its logical status, arguments, and
 * execution history. The head is a clickable button that toggles the body
 * (arguments JSON + executions list). Default collapsed.
 *
 * GAP: LogicalToolCall / ToolExecution (state/model.ts) and
 * ToolExecutionCompletedPayload (api/contracts.ts) do not carry an
 * output_artifact_id, so tool output cannot be lazy-loaded here yet. The
 * run_id prop is accepted for the future useArtifact integration but is
 * currently unused. See notes.
 */
import { useState } from "react";
import type {
  LogicalToolCall,
  LogicalToolCallStatus,
  ToolExecutionStatus,
} from "../../state/model";

export interface ToolCallCardProps {
  tool: LogicalToolCall;
  run_id: string | null;
}

interface StatusTone {
  label: string;
  tone: "green" | "gold" | "muted" | "red";
  color: string;
}

const STATUS_TONE: Record<LogicalToolCallStatus, StatusTone> = {
  committed: { label: "已提交", tone: "green", color: "#3fb950" },
  requested: { label: "已请求", tone: "gold", color: "#d29922" },
  running: { label: "运行中", tone: "gold", color: "#d29922" },
  cancelled: { label: "已取消", tone: "muted", color: "#6e7681" },
  failed: { label: "失败", tone: "red", color: "#f85149" },
};

const EXECUTION_STATUS_LABEL: Record<ToolExecutionStatus, string> = {
  started: "已启动",
  completed: "已完成",
  failed: "失败",
};

function truncate(value: string, max: number): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max)}…`;
}

export function ToolCallCard({ tool, run_id }: ToolCallCardProps): JSX.Element {
  // run_id reserved for tool-output artifact lazy-load via useArtifact once
  // the execution payload carries an output_artifact_id (G3 gap - see notes).
  void run_id;

  const [expanded, setExpanded] = useState<boolean>(false);
  const tone = STATUS_TONE[tool.status];
  const icon = tool.tool_name.charAt(0).toUpperCase() || "?";
  const argumentsJson =
    tool.arguments !== undefined
      ? JSON.stringify(tool.arguments, null, 2)
      : null;

  return (
    <article className="tool" data-tool-id={tool.tool_call_id}>
      <button
        type="button"
        className="tool-head"
        aria-expanded={expanded}
        onClick={() => setExpanded((prev) => !prev)}
      >
        <span className="tool-icon" aria-hidden="true">
          {icon}
        </span>
        <span className="tool-name">{tool.tool_name}</span>
        <span className="tool-meta">{truncate(tool.turn_id, 12)}</span>
        <span
          className="tool-status"
          data-tone={tone.tone}
          style={{ color: tone.color }}
        >
          {tone.label}
        </span>
      </button>
      {expanded && (
        <div className="tool-body">
          <span className="eyebrow">参数</span>
          {argumentsJson !== null ? (
            <pre className="tool-arguments">{argumentsJson}</pre>
          ) : (
            <div className="placeholder">无参数</div>
          )}
          <span className="eyebrow">执行记录</span>
          {tool.executions.length > 0 ? (
            <ul className="execution-list">
              {tool.executions.map((ex) => (
                <li key={ex.tool_execution_id} className="execution">
                  <code className="execution-id">{ex.tool_execution_id}</code>
                  <span className="execution-status">
                    {EXECUTION_STATUS_LABEL[ex.status]}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="placeholder">暂无执行记录</div>
          )}
        </div>
      )}
    </article>
  );
}
