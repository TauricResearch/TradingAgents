import type { LogicalToolCall } from "../../state/model";

export interface ToolProgressIndicatorProps {
  tool: LogicalToolCall | null;
}

function toolStage(tool: LogicalToolCall): string {
  if (tool.status === "committed") return "已提交";
  if (tool.status === "cancelled") return "已取消";
  if (tool.status === "failed") return "失败";
  if (tool.executions.some((execution) => execution.status === "started")) {
    return "执行中";
  }
  if (tool.executions.some((execution) => execution.status === "completed")) {
    return "等待提交";
  }
  return "排队中";
}

/**
 * Shows only a tool call represented by persisted SSE events. It deliberately
 * has no synthetic percentage: the backend does not expose tool-level work
 * units, so a determinate bar here would imply false precision.
 */
export function ToolProgressIndicator({
  tool,
}: ToolProgressIndicatorProps): JSX.Element {
  if (tool === null) {
    return (
      <div className="tool-progress tool-progress-idle" data-testid="tool-progress">
        <span className="tool-progress-dot" aria-hidden="true" />
        <span>当前没有工具调用</span>
      </div>
    );
  }

  const stage = toolStage(tool);
  const active = stage === "执行中" || stage === "排队中";
  return (
    <div
      className={active ? "tool-progress tool-progress-active" : "tool-progress"}
      data-testid="tool-progress"
    >
      <span className="tool-progress-dot" aria-hidden="true" />
      <span className="tool-progress-name">{tool.tool_name}</span>
      <span className="tool-progress-stage">{stage}</span>
    </div>
  );
}
