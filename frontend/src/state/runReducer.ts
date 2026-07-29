/**
 * F2 - Pure live/history event reducer for a single TradingAgents run.
 *
 * Deterministic: no Date.now / Math.random. Never mutates input state (all
 * updates via spread). A RunSnapshotDTO is the seed frame; events are applied
 * on top via 'event' actions. Field names match the backend wire format
 * (snake_case) and are never renamed.
 */
import { ROLE_REGISTRY } from "./model";
import type {
  ArtifactRecord,
  GraphTaskRecord,
  LogicalToolCall,
  ModelCall,
  ReducerState,
  Report,
  RoleCard,
  RoleStatus,
  RunMeta,
  ToolExecution,
  ToolExecutionStatus,
  Turn,
  TurnStatus,
  VendorCall,
} from "./model";
import type {
  AssetTypeLiteral,
  ObservationCommitV1DTO,
  PersistedEventDTO,
  ResearchDepth,
  RunSnapshotDTO,
} from "../api/contracts";

export type ReducerAction =
  | { type: "event"; event: PersistedEventDTO }
  | { type: "snapshot"; snapshot: RunSnapshotDTO }
  | { type: "reset" };

// --- primitive coercions (defensive; payload is Record<string, unknown>) ---

function str(v: unknown, d = ""): string {
  return typeof v === "string" ? v : d;
}
function num(v: unknown, d = 0): number {
  return typeof v === "number" && !Number.isNaN(v) ? v : d;
}
function optNum(v: unknown): number | undefined {
  return typeof v === "number" && !Number.isNaN(v) ? v : undefined;
}
function bool(v: unknown, d = false): boolean {
  return typeof v === "boolean" ? v : d;
}
function strArr(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}
function asStrNull(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}
function dedupeAdd(arr: string[], item: string): string[] {
  return arr.includes(item) ? arr : [...arr, item];
}
function actorIdFromRoleInstance(rid: string): string {
  const idx = rid.lastIndexOf(":");
  return idx >= 0 ? rid.slice(idx + 1) : rid;
}

// --- initial state ---

export function createInitialState(snapshot?: RunSnapshotDTO): ReducerState {
  if (!snapshot) return emptyState();
  return seedFromSnapshot(snapshot);
}

function emptyState(): ReducerState {
  const meta: RunMeta = {
    run_id: "",
    status: "created",
    ticker: "",
    asset_type: "stock",
    analysis_date: "",
    selected_analysts: [],
    research_depth: 1,
    max_debate_rounds: 1,
    max_risk_discuss_rounds: 1,
    output_language: "English",
    llm_provider: "",
    quick_think_llm: "",
    deep_think_llm: "",
    configured_keys: {},
    checkpoint_enabled: false,
    created_at: "",
    updated_at: "",
    latest_sequence: 0,
    degraded_data_sources: [],
    redaction_manifest: [],
    event_schema_version: 1,
  };
  return {
    meta,
    roles: {},
    turns: {},
    model_calls: {},
    tool_calls: {},
    vendor_calls: {},
    artifacts: {},
    reports: [],
    graph_tasks: {},
    latest_graph_step: 0,
  };
}

function seedFromSnapshot(s: RunSnapshotDTO): ReducerState {
  // Gaps: RunSnapshotDTO has no checkpoint_enabled (default false) and no
  // research_depth (default 1).
  const meta: RunMeta = {
    run_id: s.run_id,
    status: s.status,
    ticker: s.ticker,
    asset_type: s.asset_type,
    analysis_date: s.analysis_date,
    selected_analysts: [...s.selected_analysts],
    research_depth: 1,
    max_debate_rounds: s.max_debate_rounds,
    max_risk_discuss_rounds: s.max_risk_discuss_rounds,
    output_language: s.output_language,
    llm_provider: s.llm_provider,
    quick_think_llm: s.quick_think_llm,
    deep_think_llm: s.deep_think_llm,
    configured_keys: { ...s.configured_keys },
    checkpoint_enabled: false,
    created_at: s.created_at,
    updated_at: s.updated_at,
    latest_sequence: 0,  // replay all events from 0 to rebuild state
    final_signal: s.final_signal,
    final_report_artifact_id: s.final_report_artifact_id,
    completed_at: s.completed_at,
    degraded_data_sources: [...(s.degraded_data_sources ?? [])],
    summary: s.summary,
    error_category: s.error_category,
    retry_of: s.retry_of,
    resumed_from_sequence: s.resumed_from_sequence,
    resume_fingerprint: s.resume_fingerprint,
    runtime_semantics_hash: s.runtime_semantics_hash,
    agent_state_schema_sha256: s.agent_state_schema_sha256,
    redaction_manifest: [...s.redaction_manifest],
    event_schema_version: s.event_schema_version,
  };
  return {
    meta,
    roles: seedRoles(s.run_id, s.selected_analysts),
    turns: {},
    model_calls: {},
    tool_calls: {},
    vendor_calls: {},
    artifacts: {},
    reports: [],
    graph_tasks: {},
    latest_graph_step: 0,
  };
}

function seedRoles(run_id: string, selected_analysts: string[]): Record<string, RoleCard> {
  const selected = new Set(selected_analysts);
  const roles: Record<string, RoleCard> = {};
  for (const def of ROLE_REGISTRY) {
    const key = def.analyst_key;
    let status: RoleStatus;
    let reason: string | undefined;
    if (key !== null) {
      if (selected.has(key)) {
        status = "pending";
      } else {
        status = "skipped";
        reason = "not_selected";
      }
    } else {
      status = "pending";
    }
    roles[def.actor_id] = {
      actor_id: def.actor_id,
      node_id: def.node_id,
      team_id: def.team_id,
      status,
      role_instance_id: run_id ? `${run_id}:${def.actor_id}` : undefined,
      reason,
    };
  }
  return roles;
}

// --- reducer ---

export function runReducer(state: ReducerState, action: ReducerAction): ReducerState {
  switch (action.type) {
    case "reset":
      return createInitialState();
    case "snapshot":
      return createInitialState(action.snapshot);
    case "event":
      return applyEvent(state, action.event);
    default:
      return state;
  }
}

function applyEvent(state: ReducerState, event: PersistedEventDTO): ReducerState {
  if (event.sequence <= state.meta.latest_sequence) {
    return state;
  }
  const next = applyKnownEvent(state, event);
  // Bump latest_sequence + updated_at for known AND unknown types so a later
  // replay of the same event dedupes (forward-compat per spec §9.5).
  return {
    ...next,
    meta: {
      ...next.meta,
      latest_sequence: Math.max(next.meta.latest_sequence, event.sequence),
      updated_at: event.timestamp,
    },
  };
}

function applyKnownEvent(state: ReducerState, event: PersistedEventDTO): ReducerState {
  const p = event.payload;
  switch (event.type) {
    case "run.started":
      return applyRunStarted(state, event, p);
    case "run.cancel_requested":
      return { ...state, meta: { ...state.meta, status: "cancel_requested" } };
    case "run.completed":
      return applyRunTerminal(state, p, "completed");
    case "run.failed":
      return applyRunTerminal(state, p, "failed");
    case "run.cancelled":
      return applyRunTerminal(state, p, "cancelled");
    case "run.interrupted":
      return applyRunInterrupted(state);
    case "run.resumed":
      return applyRunResumed(state, p);
    case "role.status_changed":
      return applyRoleStatusChanged(state, p);
    case "turn.started":
    case "turn.output_ready":
    case "turn.completed":
    case "turn.failed":
    case "turn.cancelled":
    case "turn.interrupted":
    case "turn.resumed":
      return applyTurnEvent(state, p);
    case "model.started":
      return applyModelStarted(state, p);
    case "model.completed":
      return applyModelEnded(state, p, "completed");
    case "model.failed":
      return applyModelEnded(state, p, "failed");
    case "agent.message":
      return state; // gap: Turn has no messages field in model.ts
    case "tool.requested":
      return applyToolRequested(state, p);
    case "tool.execution_started":
      return applyToolExecution(state, p, "started");
    case "tool.execution_completed":
      return applyToolExecution(state, p, "completed");
    case "tool.execution_failed":
      return applyToolExecution(state, p, "failed");
    case "tool.committed":
      return applyToolCommitted(state, p);
    case "tool.cancelled":
      return applyToolCancelled(state, p);
    case "data.progress":
      return applyDataCall(state, p, "progress");
    case "data.completed":
      return applyDataCall(state, p, "completed");
    case "data.failed":
      return applyDataCall(state, p, "failed");
    case "data.interrupted":
      return applyDataCall(state, p, "interrupted");
    case "data.cache_hit":
      return applyDataCacheHit(state, p);
    case "input.state_snapshot":
    case "input.config_snapshot":
    case "input.prompt_snapshot":
    case "input.data_snapshot":
      return applyInputSnapshot(state, p);
    case "artifact.written":
      return applyArtifactWritten(state, event, p);
    case "report.updated":
      return applyReportUpdated(state, p);
    case "graph.task_started":
      return applyGraphTaskStarted(state, p);
    case "graph.task_output_ready":
      return applyGraphTaskOutputReady(state, p);
    case "graph.task_abandoned":
      return applyGraphTaskAbandoned(state, p);
    case "graph.step_applied":
      return applyGraphStepApplied(state, p);
    case "graph.checkpoint_committed":
      return applyGraphCheckpointCommitted(state, p);
    case "stats.updated":
      return { ...state, latest_stats: { ...p } };
    default:
      return state;
  }
}

// --- run.* ---

function applyRunStarted(
  state: ReducerState,
  event: PersistedEventDTO,
  p: Record<string, unknown>,
): ReducerState {
  const run_id = event.run_id;
  const payloadAnalysts = strArr(p.selected_analysts);
  // Fall back to state.meta when the run.started payload omits a field.
  // Older persisted runs (pre-2026-07-21) emitted run.started with only
  // run_status+retry_of; the snapshot seed already carries these values,
  // and replaying such an event must not blank them out.
  const selected_analysts =
    payloadAnalysts.length > 0 ? payloadAnalysts : state.meta.selected_analysts;
  const meta: RunMeta = {
    ...state.meta,
    run_id,
    status: "running",
    ticker: str(p.ticker, state.meta.ticker),
    asset_type: (str(p.asset_type, state.meta.asset_type) || "stock") as AssetTypeLiteral,
    analysis_date: str(p.analysis_date, state.meta.analysis_date),
    selected_analysts,
    research_depth: (num(p.research_depth, state.meta.research_depth) || 1) as ResearchDepth,
    max_debate_rounds: num(p.max_debate_rounds, state.meta.max_debate_rounds),
    max_risk_discuss_rounds: num(p.max_risk_discuss_rounds, state.meta.max_risk_discuss_rounds),
    output_language: str(p.output_language, state.meta.output_language),
    llm_provider: str(p.llm_provider, state.meta.llm_provider),
    quick_think_llm: str(p.quick_think_llm, state.meta.quick_think_llm),
    deep_think_llm: str(p.deep_think_llm, state.meta.deep_think_llm),
    checkpoint_enabled: bool(p.checkpoint_enabled, state.meta.checkpoint_enabled),
    created_at: event.timestamp,
  };
  return { ...state, meta, roles: seedRoles(run_id, selected_analysts) };
}

function applyRunTerminal(
  state: ReducerState,
  p: Record<string, unknown>,
  status: RunMeta["status"],
): ReducerState {
  const meta: RunMeta = { ...state.meta, status };
  if ("summary" in p) meta.summary = asStrNull(p.summary);
  if ("final_signal" in p) meta.final_signal = asStrNull(p.final_signal);
  if ("final_report_artifact_id" in p) {
    meta.final_report_artifact_id = asStrNull(p.final_report_artifact_id);
  }
  if ("completed_at" in p) meta.completed_at = asStrNull(p.completed_at);
  if (Array.isArray(p.degraded_data_sources)) {
    meta.degraded_data_sources = p.degraded_data_sources.filter(
      (value): value is Record<string, unknown> =>
        value !== null && typeof value === "object" && !Array.isArray(value),
    ) as unknown as NonNullable<RunMeta["degraded_data_sources"]>;
  }
  if ("error_category" in p) meta.error_category = asStrNull(p.error_category);
  return {
    ...state,
    meta,
    roles: convertStatus(state.roles, "pending", "not_reached"),
  };
}

function applyRunInterrupted(state: ReducerState): ReducerState {
  // Gap: RunMeta has no checkpoint_sequence field; payload.checkpoint_sequence
  // is not stored. Only meta.status flips and running roles -> interrupted.
  return {
    ...state,
    meta: { ...state.meta, status: "interrupted" },
    roles: convertStatus(state.roles, "running", "interrupted"),
  };
}

function applyRunResumed(state: ReducerState, p: Record<string, unknown>): ReducerState {
  const checkpoint_sequence = optNum(p.checkpoint_sequence);
  return {
    ...state,
    meta: {
      ...state.meta,
      status: "running",
      resumed_from_sequence: checkpoint_sequence ?? state.meta.resumed_from_sequence ?? null,
    },
  };
}

function convertStatus(
  roles: Record<string, RoleCard>,
  from: RoleStatus,
  to: RoleStatus,
): Record<string, RoleCard> {
  let changed = false;
  const out: Record<string, RoleCard> = {};
  for (const key of Object.keys(roles)) {
    const r = roles[key];
    if (r.status === from) {
      out[key] = { ...r, status: to, previous_status: r.status };
      changed = true;
    } else {
      out[key] = r;
    }
  }
  return changed ? out : roles;
}

// --- role.* ---

function applyRoleStatusChanged(state: ReducerState, p: Record<string, unknown>): ReducerState {
  const role_instance_id = str(p.role_instance_id);
  const actor_id = actorIdFromRoleInstance(role_instance_id);
  const def = ROLE_REGISTRY.find((r) => r.actor_id === actor_id);
  if (!def) return state;
  const existing = state.roles[actor_id];
  const new_status =
    typeof p.new_status === "string"
      ? (p.new_status as RoleStatus)
      : (existing?.status ?? "pending");
  const trigger_turn_id = typeof p.turn_id === "string" ? p.turn_id : undefined;
  const role: RoleCard = {
    actor_id: def.actor_id,
    node_id: def.node_id,
    team_id: def.team_id,
    status: new_status,
    role_instance_id,
    previous_status:
      typeof p.previous_status === "string"
        ? (p.previous_status as RoleStatus)
        : existing?.previous_status,
    reason: typeof p.reason === "string" ? p.reason : existing?.reason,
    latest_turn_id: trigger_turn_id ?? existing?.latest_turn_id,
    latest_graph_task_id: existing?.latest_graph_task_id,
  };
  return { ...state, roles: { ...state.roles, [actor_id]: role } };
}

// --- turn.* ---

function applyTurnEvent(state: ReducerState, p: Record<string, unknown>): ReducerState {
  const turn_id = str(p.turn_id);
  const role_instance_id = str(p.role_instance_id);
  const graph_task_id = str(p.graph_task_id);
  const turn_status = str(p.turn_status);
  const existing = state.turns[turn_id];
  const base: Turn = existing ?? {
    turn_id,
    role_instance_id,
    actor_id: actorIdFromRoleInstance(role_instance_id),
    graph_task_id,
    turn_index: num(p.turn_index),
    status: "started",
    model_call_ids: [],
    tool_call_ids: [],
    vendor_call_ids: [],
  };
  let turn: Turn;
  switch (turn_status) {
    case "started":
      turn = {
        ...base,
        status: "started",
        role_instance_id,
        graph_task_id,
        turn_index: num(p.turn_index),
      };
      break;
    case "output_ready":
      turn = {
        ...base,
        status: "output_ready",
        graph_task_id,
        artifact_id: str(p.artifact_id),
      };
      break;
    case "completed":
    case "failed":
    case "cancelled":
    case "interrupted":
      turn = {
        ...base,
        status: turn_status as TurnStatus,
        graph_task_id,
        reason: str(p.reason),
        duration_ms: optNum(p.duration_ms),
      };
      break;
    case "resumed":
      turn = {
        ...base,
        status: "resumed",
        graph_task_id,
        resumed_from_sequence: num(p.resumed_from_sequence),
      };
      break;
    default:
      turn = base;
  }
  const turns = { ...state.turns, [turn_id]: turn };
  const roles = linkTurnToRole(state.roles, role_instance_id, turn_id, graph_task_id);
  return { ...state, turns, roles };
}

function linkTurnToRole(
  roles: Record<string, RoleCard>,
  role_instance_id: string,
  turn_id: string,
  graph_task_id: string,
): Record<string, RoleCard> {
  const actor_id = actorIdFromRoleInstance(role_instance_id);
  const role = roles[actor_id];
  if (!role) return roles;
  return {
    ...roles,
    [actor_id]: { ...role, latest_turn_id: turn_id, latest_graph_task_id: graph_task_id },
  };
}

// --- model.* ---

function applyModelStarted(state: ReducerState, p: Record<string, unknown>): ReducerState {
  const model_call_id = str(p.model_call_id);
  const turn_id = str(p.turn_id);
  const mc: ModelCall = {
    model_call_id,
    turn_id,
    graph_task_id: str(p.graph_task_id),
    attempt_id: str(p.attempt_id),
    provider: str(p.provider),
    model: str(p.model),
    invocation_path: str(p.invocation_path),
    status: "started",
    prompt_artifact_ids: [],
  };
  const model_calls = { ...state.model_calls, [model_call_id]: mc };
  const turns = pushToTurn(state.turns, turn_id, "model_call_ids", model_call_id);
  return { ...state, model_calls, turns };
}

function applyModelEnded(
  state: ReducerState,
  p: Record<string, unknown>,
  status: "completed" | "failed",
): ReducerState {
  const model_call_id = str(p.model_call_id);
  const existing = state.model_calls[model_call_id];
  const usage =
    typeof p.usage === "object" && p.usage !== null
      ? (p.usage as Record<string, unknown>)
      : undefined;
  if (!existing) {
    const mc: ModelCall = {
      model_call_id,
      turn_id: str(p.turn_id),
      graph_task_id: str(p.graph_task_id),
      attempt_id: str(p.attempt_id),
      provider: str(p.provider),
      model: str(p.model),
      invocation_path: str(p.invocation_path),
      status,
      duration_ms: optNum(p.duration_ms),
      usage,
      prompt_artifact_ids: [],
    };
    return { ...state, model_calls: { ...state.model_calls, [model_call_id]: mc } };
  }
  return {
    ...state,
    model_calls: {
      ...state.model_calls,
      [model_call_id]: { ...existing, status, duration_ms: optNum(p.duration_ms), usage },
    },
  };
}

function pushToTurn(
  turns: Record<string, Turn>,
  turn_id: string,
  field: "model_call_ids" | "tool_call_ids" | "vendor_call_ids",
  id: string,
): Record<string, Turn> {
  const turn = turns[turn_id];
  if (!turn) return turns;
  if (turn[field].includes(id)) return turns;
  return { ...turns, [turn_id]: { ...turn, [field]: [...turn[field], id] } };
}

// --- tool.* ---

function applyToolRequested(state: ReducerState, p: Record<string, unknown>): ReducerState {
  const tool_call_id = str(p.tool_call_id);
  const turn_id = str(p.turn_id);
  const lc: LogicalToolCall = {
    tool_call_id,
    turn_id,
    graph_task_id: str(p.graph_task_id),
    attempt_id: str(p.attempt_id),
    tool_name: str(p.tool_name),
    arguments:
      typeof p.arguments === "object" && p.arguments !== null
        ? (p.arguments as Record<string, unknown>)
        : undefined,
    status: "requested",
    executions: [],
  };
  const tool_calls = { ...state.tool_calls, [tool_call_id]: lc };
  const turns = pushToTurn(state.turns, turn_id, "tool_call_ids", tool_call_id);
  return { ...state, tool_calls, turns };
}

function applyToolExecution(
  state: ReducerState,
  p: Record<string, unknown>,
  status: ToolExecutionStatus,
): ReducerState {
  const tool_call_id = str(p.tool_call_id);
  const tool_execution_id = str(p.tool_execution_id);
  const lc = state.tool_calls[tool_call_id];
  if (!lc) return state;
  const idx = lc.executions.findIndex((e) => e.tool_execution_id === tool_execution_id);
  // Upsert by tool_execution_id (deviation from literal "push": avoids
  // duplicate entries across started->completed for the same execution).
  let executions: ToolExecution[];
  if (idx >= 0) {
    executions = lc.executions.slice();
    executions[idx] = { tool_execution_id, status };
  } else {
    executions = [...lc.executions, { tool_execution_id, status }];
  }
  return {
    ...state,
    tool_calls: { ...state.tool_calls, [tool_call_id]: { ...lc, executions } },
  };
}

function applyToolCommitted(state: ReducerState, p: Record<string, unknown>): ReducerState {
  const tool_call_id = str(p.tool_call_id);
  const lc = state.tool_calls[tool_call_id];
  if (!lc) return state;
  return {
    ...state,
    tool_calls: {
      ...state.tool_calls,
      [tool_call_id]: {
        ...lc,
        status: "committed",
        checkpoint_event_id: str(p.checkpoint_event_id),
      },
    },
  };
}

function applyToolCancelled(state: ReducerState, p: Record<string, unknown>): ReducerState {
  const tool_call_id = str(p.tool_call_id);
  const lc = state.tool_calls[tool_call_id];
  if (!lc) return state;
  return {
    ...state,
    tool_calls: {
      ...state.tool_calls,
      [tool_call_id]: { ...lc, status: "cancelled", reason: str(p.reason) },
    },
  };
}

// --- data.* ---

function applyDataCall(
  state: ReducerState,
  p: Record<string, unknown>,
  status: VendorCall["status"],
): ReducerState {
  const vendor_call_id = str(p.vendor_call_id);
  const turn_id = str(p.turn_id);
  const existing = state.vendor_calls[vendor_call_id];
  const vc: VendorCall = {
    vendor_call_id,
    turn_id,
    graph_task_id: str(p.graph_task_id),
    method: str(p.method),
    vendor: str(p.vendor),
    stage: str(p.stage),
    data_status: str(p.data_status),
    status,
    duration_ms: optNum(p.duration_ms) ?? existing?.duration_ms,
    failure_code: str(p.failure_code) || existing?.failure_code,
    fallback_chain: strArr(p.fallback_chain).length > 0
      ? strArr(p.fallback_chain)
      : existing?.fallback_chain,
    cache_hit_ids: existing?.cache_hit_ids ?? [],
  };
  const vendor_calls = { ...state.vendor_calls, [vendor_call_id]: vc };
  const turns = pushToTurn(state.turns, turn_id, "vendor_call_ids", vendor_call_id);
  return { ...state, vendor_calls, turns };
}

function applyDataCacheHit(state: ReducerState, p: Record<string, unknown>): ReducerState {
  const cache_hit_id = str(p.cache_hit_id);
  const origin_ids = strArr(p.origin_vendor_call_ids);
  if (!cache_hit_id || origin_ids.length === 0) return state;
  const vendor_calls = { ...state.vendor_calls };
  let changed = false;
  for (const vid of origin_ids) {
    const vc = vendor_calls[vid];
    if (!vc) continue;
    if (vc.cache_hit_ids.includes(cache_hit_id)) continue;
    vendor_calls[vid] = { ...vc, cache_hit_ids: [...vc.cache_hit_ids, cache_hit_id] };
    changed = true;
  }
  return changed ? { ...state, vendor_calls } : state;
}

// --- input.* / artifact.* ---

function applyInputSnapshot(state: ReducerState, p: Record<string, unknown>): ReducerState {
  const artifact_id = str(p.artifact_id);
  const capture_kind = str(p.capture_kind);
  const turn_id = str(p.turn_id) || undefined;
  const attempt_id = str(p.attempt_id) || undefined;
  const model_call_id = str(p.model_call_id) || undefined;
  const existing = state.artifacts[artifact_id];
  const ar: ArtifactRecord = {
    artifact_id,
    kind: existing?.kind ?? "",
    media_type: existing?.media_type ?? "",
    content_sha256: str(p.content_sha256, existing?.content_sha256 ?? ""),
    byte_size: existing?.byte_size ?? 0,
    locator: existing?.locator ?? "",
    written_sequence: existing?.written_sequence ?? 0,
    input_capture_kinds: dedupeAdd(existing?.input_capture_kinds ?? [], capture_kind),
    turn_id: turn_id ?? existing?.turn_id,
    attempt_id: attempt_id ?? existing?.attempt_id,
    model_call_id: model_call_id ?? existing?.model_call_id,
  };
  let next: ReducerState = {
    ...state,
    artifacts: { ...state.artifacts, [artifact_id]: ar },
  };
  if (capture_kind === "prompt_snapshot") {
    const mcId = model_call_id ?? "";
    const mc = next.model_calls[mcId];
    if (mc) {
      next = {
        ...next,
        model_calls: {
          ...next.model_calls,
          [mcId]: {
            ...mc,
            prompt_artifact_ids: dedupeAdd(mc.prompt_artifact_ids, artifact_id),
          },
        },
      };
    }
  }
  return next;
}

function applyArtifactWritten(
  state: ReducerState,
  event: PersistedEventDTO,
  p: Record<string, unknown>,
): ReducerState {
  const artifact_id = str(p.artifact_id);
  const existing = state.artifacts[artifact_id];
  const ar: ArtifactRecord = {
    artifact_id,
    kind: str(p.kind, existing?.kind ?? ""),
    media_type: str(p.media_type, existing?.media_type ?? ""),
    content_sha256: str(p.content_sha256, existing?.content_sha256 ?? ""),
    byte_size: num(p.byte_size, existing?.byte_size ?? 0),
    locator: str(p.locator, existing?.locator ?? ""),
    written_sequence: event.sequence,
    input_capture_kinds: existing?.input_capture_kinds ?? [],
  };
  return { ...state, artifacts: { ...state.artifacts, [artifact_id]: ar } };
}

// --- report.* ---

function applyReportUpdated(state: ReducerState, p: Record<string, unknown>): ReducerState {
  const report: Report = {
    turn_id: str(p.turn_id),
    report_kind: str(p.report_kind),
    revision: num(p.revision),
    artifact_id: str(p.artifact_id),
  };
  return { ...state, reports: [...state.reports, report] };
}

// --- graph.* ---

function applyGraphTaskStarted(state: ReducerState, p: Record<string, unknown>): ReducerState {
  const graph_task_id = str(p.graph_task_id);
  const gt: GraphTaskRecord = {
    graph_task_id,
    graph_step: num(p.graph_step),
    node_id: str(p.node_id),
    status: "started",
    applied: false,
  };
  return { ...state, graph_tasks: { ...state.graph_tasks, [graph_task_id]: gt } };
}

function applyGraphTaskOutputReady(
  state: ReducerState,
  p: Record<string, unknown>,
): ReducerState {
  const oc =
    typeof p.observation_commit === "object" && p.observation_commit !== null
      ? (p.observation_commit as ObservationCommitV1DTO)
      : undefined;
  const graph_task_id = oc?.graph_task_id ?? str(p.graph_task_id);
  const existing = state.graph_tasks[graph_task_id];
  const patch: Partial<GraphTaskRecord> = {
    status: "output_ready",
    observation_commit: oc,
    business_delta_artifact_id: str(p.business_delta_artifact_id),
  };
  const gt: GraphTaskRecord = existing
    ? { ...existing, ...patch }
    : {
        graph_task_id,
        graph_step: num(p.graph_step),
        node_id: str(p.node_id),
        status: "output_ready",
        applied: false,
        ...patch,
      };
  return { ...state, graph_tasks: { ...state.graph_tasks, [graph_task_id]: gt } };
}

function applyGraphTaskAbandoned(state: ReducerState, p: Record<string, unknown>): ReducerState {
  const graph_task_id = str(p.graph_task_id);
  const existing = state.graph_tasks[graph_task_id];
  const reason = str(p.reason);
  const gt: GraphTaskRecord = existing
    ? { ...existing, status: "abandoned", reason }
    : {
        graph_task_id,
        graph_step: num(p.graph_step),
        node_id: str(p.node_id),
        status: "abandoned",
        applied: false,
        reason,
      };
  return { ...state, graph_tasks: { ...state.graph_tasks, [graph_task_id]: gt } };
}

function applyGraphStepApplied(state: ReducerState, p: Record<string, unknown>): ReducerState {
  const applied_ids = strArr(p.applied_task_ids);
  const graph_step = num(p.graph_step);
  const latest_graph_step = Math.max(state.latest_graph_step, graph_step);
  if (applied_ids.length === 0) {
    return { ...state, latest_graph_step };
  }
  const graph_tasks = { ...state.graph_tasks };
  for (const id of applied_ids) {
    const gt = graph_tasks[id];
    if (gt) graph_tasks[id] = { ...gt, applied: true };
  }
  return { ...state, graph_tasks, latest_graph_step };
}

function applyGraphCheckpointCommitted(
  state: ReducerState,
  p: Record<string, unknown>,
): ReducerState {
  const applied_ids = strArr(p.applied_task_ids);
  const graph_step = num(p.graph_step);
  const checkpoint_id = str(p.checkpoint_id);
  const latest_graph_step = Math.max(state.latest_graph_step, graph_step);
  const graph_tasks = { ...state.graph_tasks };
  for (const id of applied_ids) {
    const gt = graph_tasks[id];
    if (gt) graph_tasks[id] = { ...gt, applied: true, checkpoint_id };
  }
  return {
    ...state,
    graph_tasks,
    latest_graph_step,
    latest_checkpoint_id: checkpoint_id,
  };
}
