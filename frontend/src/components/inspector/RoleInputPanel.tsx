/**
 * Flat turn inspector content.
 *
 * The selected turn is presented in a fixed order with no tab state:
 * identity, evidence, prompt/LLM input, and output.  All values come from
 * reducer state or persisted artifacts; missing execution facts are rendered
 * explicitly as unavailable.
 */
import { useState } from "react";
import type {
  ArtifactRecord,
  LogicalToolCall,
  ModelCall,
  ReducerState,
  Turn,
} from "../../state/model";
import { ROLE_REGISTRY } from "../../state/model";
import { artifactsForTurn } from "../../state/selectors";
import { useWorkbenchStore } from "../../state/WorkbenchStore";
import { useArtifact } from "../../hooks/useArtifact";
import { SafeMarkdown } from "../shared/SafeMarkdown";
import { ROLE_LABELS_ZH, stageColorClass } from "../../domain/roles";
import { RoleIcon } from "../icons/RoleIcon";
import { ToolCallCard } from "../tools/ToolCallCard";
import { VendorProvenance } from "../tools/VendorProvenance";

export interface RoleInputPanelProps {
  turn_id: string | null;
}

const STATE_KIND = "state_snapshot";
const PROMPT_KIND = "prompt_snapshot";
const CONFIG_KIND = "config_snapshot";
const UNAVAILABLE = "不可用";

const TURN_STATUS_LABELS: Record<Turn["status"], string> = {
  started: "执行中",
  output_ready: "候选已就绪",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
  resumed: "已恢复",
};

function truncateId(id: string, max = 16): string {
  return id.length > max ? `${id.slice(0, max)}…` : id;
}

function parseJson(content: string | null): unknown {
  if (content === null) return null;
  try {
    return JSON.parse(content);
  } catch {
    return content;
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function sortedArtifacts(artifacts: ArtifactRecord[]): ArtifactRecord[] {
  return [...artifacts].sort(
    (left, right) =>
      left.written_sequence - right.written_sequence ||
      left.artifact_id.localeCompare(right.artifact_id),
  );
}

function formatDuration(milliseconds: number | undefined): string {
  if (milliseconds === undefined || milliseconds <= 0) return UNAVAILABLE;
  const seconds = milliseconds / 1000;
  if (seconds < 60) {
    return Number.isInteger(seconds) ? `${seconds}s` : `${seconds.toFixed(1)}s`;
  }
  const wholeSeconds = Math.round(seconds);
  return `${Math.floor(wholeSeconds / 60)}m ${wholeSeconds % 60}s`;
}

function producingModelCall(
  state: ReducerState,
  turn: Turn,
): ModelCall | null {
  for (let index = turn.model_call_ids.length - 1; index >= 0; index -= 1) {
    const call = state.model_calls[turn.model_call_ids[index]];
    if (call?.status === "completed") return call;
  }
  return null;
}

function ArtifactLineage({ artifact }: { artifact?: ArtifactRecord }): JSX.Element {
  return (
    <div className="lineage artifact-lineage">
      <div>
        <span className="eyebrow">artifact</span>
        <span>{artifact ? truncateId(artifact.artifact_id) : UNAVAILABLE}</span>
      </div>
      <div>
        <span className="eyebrow">sha256</span>
        <span className="verified">
          {artifact?.content_sha256
            ? truncateId(artifact.content_sha256, 20)
            : UNAVAILABLE}
        </span>
      </div>
      <div>
        <span className="eyebrow">locator</span>
        <span>{artifact?.locator || UNAVAILABLE}</span>
      </div>
    </div>
  );
}

function LoadingArtifact({
  run_id,
  artifact,
  children,
}: {
  run_id: string | null;
  artifact: ArtifactRecord;
  children: (content: string) => JSX.Element;
}): JSX.Element {
  const { content, loading, error } = useArtifact(run_id, artifact.artifact_id);
  if (loading) return <div className="placeholder">正在加载</div>;
  if (error !== null) return <div className="placeholder">加载失败：{error}</div>;
  if (content === null) return <div className="placeholder">（无内容）</div>;
  return children(content);
}

function FieldValue({ value }: { value: unknown }): JSX.Element {
  if (value === null || value === undefined) {
    return <div className="placeholder">{UNAVAILABLE}</div>;
  }
  if (typeof value === "string") {
    if (value.trim() === "") return <div className="placeholder">（空）</div>;
    return <SafeMarkdown content={value} mode="prose" />;
  }
  if (typeof value === "object") {
    return <SafeMarkdown content={JSON.stringify(value, null, 2)} mode="data" />;
  }
  return <span>{String(value)}</span>;
}

function StateSnapshotBody({ content }: { content: string }): JSX.Element {
  const envelope = asRecord(parseJson(content));
  const stateFields = asRecord(envelope?.state_fields);
  if (stateFields === null) {
    return (
      <div className="placeholder">
        {UNAVAILABLE}：state_snapshot 未包含可解析的 state_fields
      </div>
    );
  }
  const entries = Object.entries(stateFields);
  if (entries.length === 0) {
    return <div className="placeholder">（无上游字段）</div>;
  }
  return (
    <>
      <div className="evidence-field-index" aria-label="上游字段">
        {entries.map(([name]) => (
          <code key={name}>{name}</code>
        ))}
      </div>
      <div className="evidence-field-values" aria-label="解析后的字段值">
        {entries.map(([name, value]) => (
          <article className="evidence-field" key={name}>
            <h5>{name}</h5>
            <FieldValue value={value} />
          </article>
        ))}
      </div>
    </>
  );
}

function StateSnapshotCard({
  run_id,
  artifact,
}: {
  run_id: string | null;
  artifact: ArtifactRecord;
}): JSX.Element {
  return (
    <article className="packet state-snapshot-card">
      <div className="packet-head">
        <h4>上游状态快照</h4>
        <span>{truncateId(artifact.artifact_id)}</span>
      </div>
      <ArtifactLineage artifact={artifact} />
      <LoadingArtifact run_id={run_id} artifact={artifact}>
        {(content) => <StateSnapshotBody content={content} />}
      </LoadingArtifact>
    </article>
  );
}

function ConfigBody({ content }: { content: string }): JSX.Element {
  const parsed = asRecord(parseJson(content));
  const values = asRecord(parsed?.values) ?? parsed;
  if (values === null || Object.keys(values).length === 0) {
    return <div className="placeholder">（无配置字段）</div>;
  }
  return (
    <table className="data-table">
      <tbody>
        {Object.entries(values).map(([key, value]) => (
          <tr key={key}>
            <td className="input-ref">{key}</td>
            <td>
              {typeof value === "object"
                ? JSON.stringify(value)
                : String(value ?? UNAVAILABLE)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ConfigArtifactCard({
  run_id,
  artifact,
}: {
  run_id: string | null;
  artifact: ArtifactRecord;
}): JSX.Element {
  return (
    <article className="packet config-snapshot-card">
      <div className="packet-head">
        <h4>有效配置</h4>
        <span>{truncateId(artifact.artifact_id)}</span>
      </div>
      <ArtifactLineage artifact={artifact} />
      <LoadingArtifact run_id={run_id} artifact={artifact}>
        {(content) => <ConfigBody content={content} />}
      </LoadingArtifact>
    </article>
  );
}

function LinkedEffectiveConfig({
  state,
  run_id,
  stateArtifact,
}: {
  state: ReducerState;
  run_id: string | null;
  stateArtifact: ArtifactRecord;
}): JSX.Element {
  const stateSnapshot = useArtifact(run_id, stateArtifact.artifact_id);
  const envelope = asRecord(parseJson(stateSnapshot.content));
  const linkedId =
    typeof envelope?.effective_config_artifact_id === "string"
      ? envelope.effective_config_artifact_id
      : null;
  const linkedArtifact = linkedId ? state.artifacts[linkedId] : undefined;
  const linkedConfig = useArtifact(run_id, linkedId);

  if (stateSnapshot.loading) return <div className="placeholder">正在解析有效配置引用</div>;
  if (stateSnapshot.error !== null) {
    return <div className="placeholder">有效配置引用加载失败：{stateSnapshot.error}</div>;
  }
  if (linkedId === null) {
    return <div className="placeholder">{UNAVAILABLE}：本角色未关联有效配置快照</div>;
  }
  return (
    <article className="packet config-snapshot-card">
      <div className="packet-head">
        <h4>有效配置</h4>
        <span>{truncateId(linkedId)}</span>
      </div>
      <ArtifactLineage artifact={linkedArtifact} />
      {linkedConfig.loading ? (
        <div className="placeholder">正在加载</div>
      ) : linkedConfig.error !== null ? (
        <div className="placeholder">加载失败：{linkedConfig.error}</div>
      ) : linkedConfig.content === null ? (
        <div className="placeholder">（无内容）</div>
      ) : (
        <ConfigBody content={linkedConfig.content} />
      )}
    </article>
  );
}

function PromptArtifact({
  run_id,
  artifact,
}: {
  run_id: string | null;
  artifact: ArtifactRecord;
}): JSX.Element {
  return (
    <article className="packet prompt-artifact">
      <div className="packet-head">
        <h4>模型输入快照</h4>
        <span>{truncateId(artifact.artifact_id)}</span>
      </div>
      <ArtifactLineage artifact={artifact} />
      <LoadingArtifact run_id={run_id} artifact={artifact}>
        {(content) => <SafeMarkdown content={content} mode="data" />}
      </LoadingArtifact>
    </article>
  );
}

function OutputArtifact({
  run_id,
  artifact,
}: {
  run_id: string | null;
  artifact: ArtifactRecord;
}): JSX.Element {
  return (
    <article className="packet output-artifact">
      <div className="packet-head">
        <h4>Response artifact</h4>
        <span>{truncateId(artifact.artifact_id)}</span>
      </div>
      <ArtifactLineage artifact={artifact} />
      <LoadingArtifact run_id={run_id} artifact={artifact}>
        {(content) => <SafeMarkdown content={content} mode="prose" />}
      </LoadingArtifact>
    </article>
  );
}

function IdentitySection({
  state,
  turn,
}: {
  state: ReducerState;
  turn: Turn;
}): JSX.Element {
  const roleDef = ROLE_REGISTRY.find((role) => role.actor_id === turn.actor_id);
  const label = ROLE_LABELS_ZH[turn.actor_id] ?? roleDef?.display_name ?? turn.actor_id;
  const modelCall = producingModelCall(state, turn);
  return (
    <section className="inspector-section inspector-identity" aria-labelledby="inspector-identity-title">
      <div className="inspector-section-heading">
        <span className="eyebrow">Identity</span>
        <h3 id="inspector-identity-title">角色与执行事实</h3>
      </div>
      <div className="role-header">
        <div className={`role-badge ${stageColorClass(turn.actor_id)}`}>
          <RoleIcon icon_id={roleDef?.icon_id ?? ""} size={18} />
        </div>
        <div>
          <div className="role-title">{label}</div>
          <div className="role-sub">{truncateId(turn.turn_id)} · {turn.actor_id}</div>
        </div>
      </div>
      <dl className="identity-facts">
        <div><dt>轮次</dt><dd>{turn.turn_index > 0 ? `第 ${turn.turn_index} 轮` : UNAVAILABLE}</dd></div>
        <div><dt>状态</dt><dd>{TURN_STATUS_LABELS[turn.status] ?? turn.status}</dd></div>
        <div><dt>耗时</dt><dd>{formatDuration(turn.duration_ms)}</dd></div>
        <div><dt>Provider</dt><dd>{modelCall?.provider || UNAVAILABLE}</dd></div>
        <div><dt>Model</dt><dd>{modelCall?.model || UNAVAILABLE}</dd></div>
      </dl>
    </section>
  );
}

function EvidenceSection({
  state,
  run_id,
  turn,
  artifacts,
}: {
  state: ReducerState;
  run_id: string | null;
  turn: Turn;
  artifacts: ArtifactRecord[];
}): JSX.Element {
  const stateArtifacts = sortedArtifacts(
    artifacts.filter((artifact) => artifact.input_capture_kinds.includes(STATE_KIND)),
  );
  const configArtifacts = sortedArtifacts(
    artifacts.filter((artifact) => artifact.input_capture_kinds.includes(CONFIG_KIND)),
  );
  const tools: LogicalToolCall[] = turn.tool_call_ids
    .map((id) => state.tool_calls[id])
    .filter((tool): tool is LogicalToolCall => tool !== undefined);

  return (
    <section className="inspector-section inspector-evidence" aria-labelledby="inspector-evidence-title">
      <div className="inspector-section-heading">
        <span className="eyebrow">Evidence</span>
        <h3 id="inspector-evidence-title">证据、数据与工具</h3>
      </div>

      <div className="inspector-subsection">
        <h4>上游状态字段与解析值</h4>
        <p className="section-note">
          独立的 input.data_snapshot 当前没有生产者；以下字段和值来自 state_snapshot 的 state_fields。
        </p>
        {stateArtifacts.length === 0 ? (
          <div className="placeholder">{UNAVAILABLE}：本轮未捕获 state_snapshot</div>
        ) : (
          stateArtifacts.map((artifact) => (
            <StateSnapshotCard key={artifact.artifact_id} run_id={run_id} artifact={artifact} />
          ))
        )}
      </div>

      <div className="inspector-subsection">
        <h4>工具调用与结果</h4>
        {tools.length === 0 ? (
          <div className="placeholder">未调用工具</div>
        ) : (
          tools.map((tool) => (
            <ToolCallCard key={tool.tool_call_id} tool={tool} run_id={run_id} />
          ))
        )}
      </div>

      <div className="inspector-subsection">
        <h4>数据供应商来源</h4>
        <VendorProvenance turn_id={turn.turn_id} />
      </div>

      <div className="inspector-subsection">
        <h4>有效配置</h4>
        {configArtifacts.length > 0 ? (
          configArtifacts.map((artifact) => (
            <ConfigArtifactCard key={artifact.artifact_id} run_id={run_id} artifact={artifact} />
          ))
        ) : stateArtifacts[0] ? (
          <LinkedEffectiveConfig state={state} run_id={run_id} stateArtifact={stateArtifacts[0]} />
        ) : (
          <div className="placeholder">{UNAVAILABLE}：本角色未发布有效配置快照</div>
        )}
      </div>
    </section>
  );
}

function PromptSection({
  run_id,
  artifacts,
  modelCall,
}: {
  run_id: string | null;
  artifacts: ArtifactRecord[];
  modelCall: ModelCall | null;
}): JSX.Element {
  const [open, setOpen] = useState(false);
  const promptArtifacts = sortedArtifacts(
    artifacts.filter((artifact) => artifact.input_capture_kinds.includes(PROMPT_KIND)),
  );
  const producerPromptIds = new Set(modelCall?.prompt_artifact_ids ?? []);
  const orderedPrompts = [...promptArtifacts].sort((left, right) => {
    const leftRank = producerPromptIds.has(left.artifact_id) ? 0 : 1;
    const rightRank = producerPromptIds.has(right.artifact_id) ? 0 : 1;
    return leftRank - rightRank || left.written_sequence - right.written_sequence;
  });

  return (
    <details className="inspector-section inspector-prompt" open={open}>
      <summary
        onClick={(event) => {
          event.preventDefault();
          setOpen((value) => !value);
        }}
      >
        <span>
          <span className="eyebrow">Prompt / LLM input</span>
          <strong>模型实际输入</strong>
        </span>
        <span className="placeholder">{open ? "已展开" : "默认折叠"}</span>
      </summary>
      {open && (
        <div className="inspector-section-body">
          {orderedPrompts.length === 0 ? (
            <div className="placeholder">{UNAVAILABLE}：本轮未捕获 prompt_snapshot</div>
          ) : (
            orderedPrompts.map((artifact) => (
              <PromptArtifact key={artifact.artifact_id} run_id={run_id} artifact={artifact} />
            ))
          )}
        </div>
      )}
    </details>
  );
}

function OutputSection({
  state,
  run_id,
  turn,
}: {
  state: ReducerState;
  run_id: string | null;
  turn: Turn;
}): JSX.Element {
  const artifact = turn.artifact_id ? state.artifacts[turn.artifact_id] : undefined;
  return (
    <section className="inspector-section inspector-output" aria-labelledby="inspector-output-title">
      <div className="inspector-section-heading">
        <span className="eyebrow">Output</span>
        <h3 id="inspector-output-title">角色输出</h3>
      </div>
      {!turn.artifact_id ? (
        <div className="placeholder">{UNAVAILABLE}：当前 turn 尚未发布 response artifact</div>
      ) : artifact ? (
        <OutputArtifact run_id={run_id} artifact={artifact} />
      ) : (
        <div className="placeholder">
          {UNAVAILABLE}：response artifact {truncateId(turn.artifact_id)} 尚未写入索引
        </div>
      )}
    </section>
  );
}

export function RoleInputPanel({ turn_id }: RoleInputPanelProps): JSX.Element {
  const { stream, run_id } = useWorkbenchStore();
  const state = stream.state;

  if (turn_id === null || state === null || state.turns[turn_id] === undefined) {
    return <div className="placeholder inspector-empty">选择一个发言查看完整审计信息</div>;
  }

  const turn = state.turns[turn_id];
  const artifacts = artifactsForTurn(state, turn_id);
  const modelCall = producingModelCall(state, turn);

  return (
    <div className="turn-inspector" data-turn-id={turn_id}>
      <IdentitySection state={state} turn={turn} />
      <EvidenceSection state={state} run_id={run_id} turn={turn} artifacts={artifacts} />
      <PromptSection run_id={run_id} artifacts={artifacts} modelCall={modelCall} />
      <OutputSection state={state} run_id={run_id} turn={turn} />
    </div>
  );
}
