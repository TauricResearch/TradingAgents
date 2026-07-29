/**
 * G3 - contextual audit view for a selected turn's actual inputs.
 *
 * Renders the role header (icon + Chinese label + turn status) and a compact
 * audit panel that lazy-loads artifact content per tab:
 *   上游资料  - state_snapshot artifacts as the role's actual upstream fields
 *   Prompt    - prompt_snapshot artifacts as preformatted text
 *   配置      - config_snapshot artifacts when the role has one
 *
 * Artifacts are joined to the turn via ArtifactRecord.turn_id (populated by
 * the reducer from input.* events) and filtered through artifactsForTurn.
 */
import { useState } from "react";
import type { ArtifactRecord } from "../../state/model";
import { ROLE_REGISTRY } from "../../state/model";
import { artifactsForTurn } from "../../state/selectors";
import { useWorkbenchStore } from "../../state/WorkbenchStore";
import { useArtifact } from "../../hooks/useArtifact";
import { ROLE_LABELS_ZH, stageColorClass } from "../../domain/roles";
import { RoleIcon } from "../icons/RoleIcon";

export interface RoleInputPanelProps {
  turn_id: string | null;
}

type AuditTab = "state" | "prompt" | "config";

const BASE_TABS: ReadonlyArray<{ id: AuditTab; label: string }> = [
  { id: "state", label: "上游资料" },
  { id: "prompt", label: "Prompt" },
];

const STATE_KIND = "state_snapshot";
const PROMPT_KIND = "prompt_snapshot";
const CONFIG_KIND = "config_snapshot";

function truncateId(id: string, max = 12): string {
  return id.length > max ? `${id.slice(0, max)}…` : id;
}

/** Parse artifact content as JSON; fall back to the raw string if not JSON. */
function parseJson(content: string | null): unknown {
  if (content === null) return null;
  try {
    return JSON.parse(content);
  } catch {
    return content;
  }
}

/** Flatten a parsed JSON value into [key, stringified-value] rows. */
function flattenToRows(value: unknown): Array<[string, string]> {
  if (value === null || value === undefined) return [];
  if (typeof value !== "object" || Array.isArray(value)) {
    return [
      ["value", typeof value === "string" ? value : JSON.stringify(value)],
    ];
  }
  const obj = value as Record<string, unknown>;
  const rows: Array<[string, string]> = [];
  for (const key of Object.keys(obj)) {
    const v = obj[key];
    if (v === null || v === undefined) {
      rows.push([key, "-"]);
    } else if (typeof v === "object") {
      rows.push([key, JSON.stringify(v)]);
    } else {
      rows.push([key, String(v)]);
    }
  }
  return rows;
}

function KeyValueTable({ content }: { content: string | null }): JSX.Element {
  if (content === null) {
    return <div className="placeholder">（无内容）</div>;
  }
  const rows = flattenToRows(parseJson(content));
  if (rows.length === 0) {
    return <div className="placeholder">（无字段）</div>;
  }
  return (
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
  );
}

function PromptBody({ content }: { content: string | null }): JSX.Element {
  if (content === null) {
    return <div className="placeholder">（无内容）</div>;
  }
  // Prompt snapshots are raw model input, not a report: preserve exact
  // whitespace instead of treating model-provided text as presentation markup.
  return <pre className="tool-body">{content}</pre>;
}

function renderBody(
  variant: AuditTab,
  content: string | null,
): JSX.Element {
  switch (variant) {
    case "state":
      return <KeyValueTable content={content} />;
    case "prompt":
      return <PromptBody content={content} />;
    case "config":
      return <KeyValueTable content={content} />;
    default:
      return <div className="placeholder">未知视图</div>;
  }
}

function ArtifactCard({
  run_id,
  artifact,
  variant,
  model_label,
}: {
  run_id: string | null;
  artifact: ArtifactRecord;
  variant: AuditTab;
  model_label?: string;
}): JSX.Element {
  const { content, loading, error } = useArtifact(run_id, artifact.artifact_id);

  let body: JSX.Element;
  if (loading) {
    body = <div className="placeholder">正在加载</div>;
  } else if (error !== null) {
    body = <div className="placeholder">加载失败：{error}</div>;
  } else {
    body = renderBody(variant, content);
  }

  return (
    <div className="packet">
      <div className="packet-head">
        <span className="eyebrow">{artifact.kind}</span>
        <span className="placeholder">{truncateId(artifact.artifact_id)}</span>
      </div>
      {model_label && <div className="role-sub">{model_label}</div>}
      {body}
    </div>
  );
}

export function RoleInputPanel({
  turn_id,
}: RoleInputPanelProps): JSX.Element {
  const { stream, run_id } = useWorkbenchStore();
  const state = stream.state;
  const [activeTab, setActiveTab] = useState<AuditTab>("state");

  if (
    turn_id === null ||
    state === null ||
    state.turns[turn_id] === undefined
  ) {
    return <div className="placeholder">选择一个角色查看其实际输入</div>;
  }

  const turn = state.turns[turn_id];
  const actor_id = turn.actor_id;
  const roleDef = ROLE_REGISTRY.find((r) => r.actor_id === actor_id);
  const icon_id = roleDef?.icon_id ?? "";
  const label = ROLE_LABELS_ZH[actor_id] ?? actor_id;

  const artifacts = artifactsForTurn(state, turn_id);
  const stateArts = artifacts.filter((a) =>
    a.input_capture_kinds.includes(STATE_KIND),
  );
  const promptArts = artifacts.filter((a) =>
    a.input_capture_kinds.includes(PROMPT_KIND),
  );
  const configArts = artifacts.filter((a) =>
    a.input_capture_kinds.includes(CONFIG_KIND),
  );
  const tabs = configArts.length > 0
    ? [...BASE_TABS, { id: "config" as const, label: "配置" }]
    : BASE_TABS;

  const activeArtifacts =
    activeTab === "state"
      ? stateArts
      : activeTab === "prompt"
        ? promptArts
        : configArts;

  return (
    <>
      <div className="role-header">
        <div className={`role-badge ${stageColorClass(actor_id)}`}>
          <RoleIcon icon_id={icon_id} size={18} />
        </div>
        <div>
          <div className="role-title">{label}</div>
          <div className="role-sub">
            {truncateId(turn_id)} · {turn.status}
          </div>
        </div>
      </div>

      <div className="audit-tabs">
        {tabs.map((tab) => (
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
        {activeArtifacts.length === 0 ? (
          <div className="placeholder">该视图暂无数据</div>
        ) : (
          activeArtifacts.map((art) => (
            <ArtifactCard
              key={art.artifact_id}
              run_id={run_id}
              artifact={art}
              variant={activeTab}
              model_label={
                art.model_call_id && state.model_calls[art.model_call_id]
                  ? `${state.model_calls[art.model_call_id].provider} · ${state.model_calls[art.model_call_id].model}`
                  : undefined
              }
            />
          ))
        )}
      </div>
    </>
  );
}
