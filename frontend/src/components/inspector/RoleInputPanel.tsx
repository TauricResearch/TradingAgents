/**
 * G3 - 5-tab audit view for a selected turn's actual inputs.
 *
 * Renders the role header (icon + Chinese label + turn status) and a 5-tab
 * audit panel that lazy-loads artifact content per tab:
 *   数据字段  - data_snapshot artifacts as key/value tables
 *   上游资料  - state_snapshot artifacts as field-name cards
 *   Prompt    - prompt_snapshot artifacts as preformatted text
 *   原始值    - data_snapshot artifacts with vendor/sha256/locator lineage
 *   配置      - config_snapshot artifacts as key/value tables
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
import { SafeMarkdown } from "../shared/SafeMarkdown";
import { ROLE_LABELS_ZH, stageColorClass } from "../../domain/roles";
import { RoleIcon } from "../icons/RoleIcon";

export interface RoleInputPanelProps {
  turn_id: string | null;
}

type AuditTab = "data" | "state" | "prompt" | "raw" | "config";

const TABS: ReadonlyArray<{ id: AuditTab; label: string }> = [
  { id: "data", label: "数据字段" },
  { id: "state", label: "上游资料" },
  { id: "prompt", label: "Prompt" },
  { id: "raw", label: "原始值" },
  { id: "config", label: "配置" },
];

const DATA_KIND = "data_snapshot";
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

/** Try to extract a vendor name from common payload field names. */
function extractVendor(parsed: unknown): string | null {
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return null;
  }
  const obj = parsed as Record<string, unknown>;
  const v = obj.vendor ?? obj.data_vendor ?? obj.source ?? obj.provider;
  return typeof v === "string" ? v : null;
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

function StateRefs({ content }: { content: string | null }): JSX.Element {
  if (content === null) {
    return <div className="placeholder">（无内容）</div>;
  }
  const parsed = parseJson(content);
  if (
    parsed === null ||
    typeof parsed !== "object" ||
    Array.isArray(parsed)
  ) {
    return <div className="placeholder">{content}</div>;
  }
  const fields = Object.keys(parsed as Record<string, unknown>);
  if (fields.length === 0) {
    return <div className="placeholder">（无字段）</div>;
  }
  return (
    <div className="profile-grid">
      {fields.map((f) => (
        <div key={f} className="profile-cell input-ref">
          {f}
        </div>
      ))}
    </div>
  );
}

function PromptBody({ content }: { content: string | null }): JSX.Element {
  if (content === null) {
    return <div className="placeholder">（无内容）</div>;
  }
  return <SafeMarkdown content={content} mode="data" />;
}

function RawBody({
  content,
  artifact,
}: {
  content: string | null;
  artifact: ArtifactRecord;
}): JSX.Element {
  const parsed = content === null ? null : parseJson(content);
  const vendor = extractVendor(parsed);
  const rows = content === null ? [] : flattenToRows(parsed);
  return (
    <div>
      <div className="lineage">
        <div>
          <span className="eyebrow">vendor</span>
          <span>{vendor ?? "-"}</span>
        </div>
        <div>
          <span className="eyebrow">sha256</span>
          <span className="verified">
            {truncateId(artifact.content_sha256, 16)}
          </span>
        </div>
        <div>
          <span className="eyebrow">locator</span>
          <span>{artifact.locator}</span>
        </div>
      </div>
      {rows.length > 0 && (
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
      )}
    </div>
  );
}

function renderBody(
  variant: AuditTab,
  content: string | null,
  artifact: ArtifactRecord,
): JSX.Element {
  switch (variant) {
    case "data":
      return <KeyValueTable content={content} />;
    case "state":
      return <StateRefs content={content} />;
    case "prompt":
      return <PromptBody content={content} />;
    case "raw":
      return <RawBody content={content} artifact={artifact} />;
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
}: {
  run_id: string | null;
  artifact: ArtifactRecord;
  variant: AuditTab;
}): JSX.Element {
  const { content, loading, error } = useArtifact(run_id, artifact.artifact_id);

  let body: JSX.Element;
  if (loading) {
    body = <div className="placeholder">正在加载</div>;
  } else if (error !== null) {
    body = <div className="placeholder">加载失败：{error}</div>;
  } else {
    body = renderBody(variant, content, artifact);
  }

  return (
    <div className="packet">
      <div className="packet-head">
        <span className="eyebrow">{artifact.kind}</span>
        <span className="placeholder">{truncateId(artifact.artifact_id)}</span>
      </div>
      {body}
    </div>
  );
}

export function RoleInputPanel({
  turn_id,
}: RoleInputPanelProps): JSX.Element {
  const { stream, run_id } = useWorkbenchStore();
  const state = stream.state;
  const [activeTab, setActiveTab] = useState<AuditTab>("data");

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
  const dataArts = artifacts.filter((a) =>
    a.input_capture_kinds.includes(DATA_KIND),
  );
  const stateArts = artifacts.filter((a) =>
    a.input_capture_kinds.includes(STATE_KIND),
  );
  const promptArts = artifacts.filter((a) =>
    a.input_capture_kinds.includes(PROMPT_KIND),
  );
  const configArts = artifacts.filter((a) =>
    a.input_capture_kinds.includes(CONFIG_KIND),
  );

  const activeArtifacts =
    activeTab === "data" || activeTab === "raw"
      ? dataArts
      : activeTab === "state"
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
        {TABS.map((tab) => (
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
            />
          ))
        )}
      </div>
    </>
  );
}
