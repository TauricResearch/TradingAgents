/**
 * G3 - Right-column audit inspector container with top-level tabs.
 *
 * Tabs:
 *   角色输入  - RoleInputPanel for the selected turn
 *   数据与工具 - Tool call cards (placeholder; G3-Tools integration)
 *   产物      - state.reports list with click-to-load artifact content
 *   本次输入  - Immutable run input snapshot (state.meta)
 *
 * Consumes useWorkbenchStore for state + run_id; receives selectedTurnId from
 * the layout (WorkbenchLayout holds the internal selectedTurn state).
 */
import { useState } from "react";
import type { ReducerState, Report } from "../../state/model";
import { useWorkbenchStore } from "../../state/WorkbenchStore";
import { useArtifact } from "../../hooks/useArtifact";
import { RoleInputPanel } from "./RoleInputPanel";

export interface InspectorProps {
  selectedTurnId: string | null;
}

type InspectorTab = "role-input" | "tools" | "artifacts" | "run-input";

const INSPECTOR_TABS: ReadonlyArray<{ id: InspectorTab; label: string }> = [
  { id: "role-input", label: "角色输入" },
  { id: "tools", label: "数据与工具" },
  { id: "artifacts", label: "产物" },
  { id: "run-input", label: "本次输入" },
];

function truncateId(id: string, max = 12): string {
  return id.length > max ? `${id.slice(0, max)}…` : id;
}

function ReportBody({
  run_id,
  artifact_id,
}: {
  run_id: string | null;
  artifact_id: string;
}): JSX.Element {
  const { content, loading, error } = useArtifact(run_id, artifact_id);
  if (loading) {
    return <div className="placeholder">正在加载</div>;
  }
  if (error !== null) {
    return <div className="placeholder">加载失败：{error}</div>;
  }
  if (content === null) {
    return <div className="placeholder">（无内容）</div>;
  }
  return <pre className="tool-body">{content}</pre>;
}

function ReportCard({
  report,
  run_id,
}: {
  report: Report;
  run_id: string | null;
}): JSX.Element {
  const [expanded, setExpanded] = useState<boolean>(false);
  return (
    <div className="packet">
      <div
        className="packet-head"
        style={{ cursor: "pointer" }}
        onClick={() => setExpanded((e) => !e)}
      >
        <span className="eyebrow">{report.report_kind}</span>
        <span className="placeholder">rev {report.revision}</span>
      </div>
      <div className="role-sub">{truncateId(report.artifact_id)}</div>
      {expanded && (
        <ReportBody run_id={run_id} artifact_id={report.artifact_id} />
      )}
    </div>
  );
}

function ArtifactsTab({
  state,
  run_id,
}: {
  state: ReducerState | null;
  run_id: string | null;
}): JSX.Element {
  if (state === null) {
    return <div className="placeholder">未选择运行</div>;
  }
  const reports = state.reports;
  if (reports.length === 0) {
    return <div className="placeholder">暂无产物</div>;
  }
  return (
    <div>
      {reports.map((r) => (
        <ReportCard
          key={`${r.turn_id}-${r.report_kind}-${r.revision}`}
          report={r}
          run_id={run_id}
        />
      ))}
    </div>
  );
}

function RunInputTab({ state }: { state: ReducerState | null }): JSX.Element {
  if (state === null) {
    return <div className="placeholder">未选择运行</div>;
  }
  const meta = state.meta;
  const rows: Array<[string, string]> = [
    ["run_id", meta.run_id],
    ["ticker", meta.ticker],
    ["asset_type", meta.asset_type],
    ["analysis_date", meta.analysis_date],
    ["selected_analysts", meta.selected_analysts.join(", ")],
    ["provider", meta.llm_provider],
    ["models", `${meta.quick_think_llm} / ${meta.deep_think_llm}`],
    ["language", meta.output_language],
    ["checkpoint_enabled", String(meta.checkpoint_enabled)],
    ["created_at", meta.created_at],
  ];
  return (
    <div className="packet">
      <div className="packet-head">
        <span className="eyebrow">Run input</span>
      </div>
      <table className="data-table">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}>
              <td className="input-ref">{k}</td>
              <td>{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Inspector({ selectedTurnId }: InspectorProps): JSX.Element {
  const { stream, run_id } = useWorkbenchStore();
  const state = stream.state;
  const [activeTab, setActiveTab] = useState<InspectorTab>("role-input");

  return (
    <div className="inspector">
      <div className="inspector-tabs">
        {INSPECTOR_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={activeTab === tab.id ? "active" : ""}
            aria-pressed={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="snapshot">
        {activeTab === "role-input" && (
          <RoleInputPanel turn_id={selectedTurnId} />
        )}
        {activeTab === "tools" && (
          <div className="placeholder">工具调用卡片待接入</div>
        )}
        {activeTab === "artifacts" && (
          <ArtifactsTab state={state} run_id={run_id} />
        )}
        {activeTab === "run-input" && <RunInputTab state={state} />}
      </div>
    </div>
  );
}
