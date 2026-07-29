/** Run-scoped immutable inputs and persisted artifact index. */
import { useState } from "react";
import type { ArtifactRecord, ReducerState, Report } from "../../state/model";
import { useArtifact } from "../../hooks/useArtifact";
import { ROLE_LABELS_ZH } from "../../domain/roles";
import { SafeMarkdown } from "../shared/SafeMarkdown";

export interface RunDisclosureProps {
  state: ReducerState;
}

function truncateId(id: string, max = 16): string {
  return id.length > max ? `${id.slice(0, max)}…` : id;
}

function ReportBody({ run_id, artifact_id }: { run_id: string; artifact_id: string }): JSX.Element {
  const { content, loading, error } = useArtifact(run_id, artifact_id);
  if (loading) return <div className="placeholder">正在加载</div>;
  if (error !== null) return <div className="placeholder">加载失败：{error}</div>;
  if (content === null) return <div className="placeholder">（无内容）</div>;
  return <SafeMarkdown content={content} mode="prose" />;
}

function RunInput({ state }: { state: ReducerState }): JSX.Element {
  const { meta } = state;
  const rows: Array<[string, string]> = [
    ["run_id", meta.run_id],
    ["ticker", meta.ticker],
    ["asset_type", meta.asset_type],
    ["analysis_date", meta.analysis_date],
    ["selected_analysts", meta.selected_analysts.join(", ")],
    ["research_depth", String(meta.research_depth)],
    ["debate_rounds", String(meta.max_debate_rounds)],
    ["risk_rounds", String(meta.max_risk_discuss_rounds)],
    ["provider", meta.llm_provider],
    ["models", `${meta.quick_think_llm} / ${meta.deep_think_llm}`],
    ["language", meta.output_language],
    ["checkpoint_enabled", String(meta.checkpoint_enabled)],
    ["created_at", meta.created_at],
  ];
  return (
    <section className="run-disclosure-section" aria-labelledby="run-input-title">
      <h3 id="run-input-title">本次输入</h3>
      <table className="data-table">
        <tbody>
          {rows.map(([key, value]) => (
            <tr key={key}>
              <td className="input-ref">{key}</td>
              <td>{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function reportActorLabel(state: ReducerState, report: Report): string {
  const actorId = state.turns[report.turn_id]?.actor_id;
  return actorId ? ROLE_LABELS_ZH[actorId] ?? actorId : "角色不可用";
}

function PublishedReport({
  state,
  report,
}: {
  state: ReducerState;
  report: Report;
}): JSX.Element {
  const [open, setOpen] = useState(false);
  return (
    <details
      className="packet run-report"
      open={open}
      key={`${report.turn_id}-${report.report_kind}-${report.revision}`}
    >
      <summary
        onClick={(event) => {
          event.preventDefault();
          setOpen((value) => !value);
        }}
      >
        <span>
          <strong>{reportActorLabel(state, report)}</strong>
          <span>{report.report_kind} · rev {report.revision}</span>
        </span>
        <code>{truncateId(report.artifact_id)}</code>
      </summary>
      {open && (
        <ReportBody run_id={state.meta.run_id} artifact_id={report.artifact_id} />
      )}
    </details>
  );
}

function PublishedReports({ state }: { state: ReducerState }): JSX.Element {
  const reports = [...state.reports].sort(
    (left, right) =>
      left.turn_id.localeCompare(right.turn_id) ||
      left.report_kind.localeCompare(right.report_kind) ||
      left.revision - right.revision,
  );
  return (
    <section className="run-disclosure-section" aria-labelledby="published-reports-title">
      <h3 id="published-reports-title">已发布报告</h3>
      <p className="section-note">
        仅列出通过 report.updated 发布的报告；未出现的角色不表示没有执行，只表示没有已发布报告。
      </p>
      {reports.length === 0 ? (
        <div className="placeholder">暂无已发布报告</div>
      ) : (
        <div className="run-report-list">
          {reports.map((report) => (
            <PublishedReport
              key={`${report.turn_id}-${report.report_kind}-${report.revision}`}
              state={state}
              report={report}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function ArtifactIndex({ artifacts }: { artifacts: ArtifactRecord[] }): JSX.Element {
  const ordered = [...artifacts].sort(
    (left, right) =>
      left.written_sequence - right.written_sequence ||
      left.artifact_id.localeCompare(right.artifact_id),
  );
  return (
    <section className="run-disclosure-section" aria-labelledby="artifact-index-title">
      <h3 id="artifact-index-title">完整 Artifact 索引</h3>
      {ordered.length === 0 ? (
        <div className="placeholder">暂无持久化 artifact</div>
      ) : (
        <table className="data-table artifact-index-table">
          <thead>
            <tr>
              <th scope="col">Kind</th>
              <th scope="col">Artifact</th>
              <th scope="col">SHA-256</th>
              <th scope="col">Bytes</th>
              <th scope="col">Locator</th>
            </tr>
          </thead>
          <tbody>
            {ordered.map((artifact) => (
              <tr key={artifact.artifact_id}>
                <td>{artifact.kind || "不可用"}</td>
                <td><code>{truncateId(artifact.artifact_id)}</code></td>
                <td><code>{artifact.content_sha256 ? truncateId(artifact.content_sha256, 20) : "不可用"}</code></td>
                <td>{artifact.byte_size > 0 ? artifact.byte_size : "不可用"}</td>
                <td>{artifact.locator || "不可用"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export function RunDisclosure({ state }: RunDisclosureProps): JSX.Element {
  return (
    <details className="run-disclosure">
      <summary>
        <span>运行输入与产物</span>
        <span className="placeholder">{state.reports.length} 份已发布报告 · {Object.keys(state.artifacts).length} 个 artifacts</span>
      </summary>
      <div className="run-disclosure-body">
        <RunInput state={state} />
        <PublishedReports state={state} />
        <ArtifactIndex artifacts={Object.values(state.artifacts)} />
      </div>
    </details>
  );
}
