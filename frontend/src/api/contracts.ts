/**
 * F2 — TradingAgents frontend/backend wire contracts.
 *
 * Single source of truth: backend Python
 *   tradingagents/observability/events.py
 *   tradingagents/observability/roles.py
 *   tradingagents/web/run_models.py
 *   tradingagents/web/schemas.py
 *   tradingagents/web/api.py
 *
 * Field names are snake_case-matched to the backend wire format. The reducer
 * MUST NOT rename keys. `any` is only used where the backend emits an opaque
 * blob that the frontend never interprets (explicitly justified inline).
 */

// ---------------------------------------------------------------------------
// Transport constants
// ---------------------------------------------------------------------------

/** Same-origin: the SPA is served by the FastAPI app itself. */
export const SERVER_HTTP_BASE = "";

export const API = {
  config: "/api/config",
  runs: "/api/runs",
  run: (run_id: string) => `/api/runs/${run_id}`,
  cancel: (run_id: string) => `/api/runs/${run_id}/cancel`,
  retry: (run_id: string) => `/api/runs/${run_id}/retry`,
  resume: (run_id: string) => `/api/runs/${run_id}/resume`,
  artifacts: (run_id: string) => `/api/runs/${run_id}/artifacts`,
  artifact: (run_id: string, artifact_id: string) =>
    `/api/runs/${run_id}/artifacts/${artifact_id}`,
  events: (run_id: string, after?: number) =>
    `/api/runs/${run_id}/events${after != null ? `?after=${after}` : ""}`,
} as const;

export const EVENT_SCHEMA_VERSION = 1 as const;

/** SSE terminal events — the stream is closed by the server after these. */
export const TERMINAL_STREAM_EVENTS = [
  "run.completed",
  "run.failed",
  "run.cancelled",
  "run.interrupted",
] as const;

export type TerminalStreamEventType = (typeof TERMINAL_STREAM_EVENTS)[number];

// ---------------------------------------------------------------------------
// /api/config
// ---------------------------------------------------------------------------

export interface ModelOptionDTO {
  label: string;
  id: string;
}

export interface ProviderModelOptionsDTO {
  quick: ModelOptionDTO[];
  deep: ModelOptionDTO[];
}

export interface ProviderDTO {
  id: string;
  configured: boolean;
  requires_api_key: boolean;
  models: ProviderModelOptionsDTO;
  custom_model_allowed: boolean;
}

export interface AnalystOptionDTO {
  id: string;
}

export interface ConfigDefaultsDTO {
  llm_provider: string | null;
  quick_think_llm: string | null;
  deep_think_llm: string | null;
  output_language: string;
  research_depth: number;
  checkpoint_enabled: boolean;
}

export interface ConfigResponseDTO {
  providers: ProviderDTO[];
  configured_keys: Record<string, boolean>;
  analysts: AnalystOptionDTO[];
  depths: number[];
  output_languages: string[];
  checkpoint_available: boolean;
  defaults: ConfigDefaultsDTO;
}

// ---------------------------------------------------------------------------
// Run create request (RunCreateRequest — pydantic, extra="forbid")
// ---------------------------------------------------------------------------

export type ResearchDepth = 1 | 3 | 5;
export type AssetTypeLiteral = "stock" | "crypto";

export interface RunCreateRequestDTO {
  ticker: string;
  analysis_date: string;
  selected_analysts: string[];
  research_depth: ResearchDepth;
  llm_provider: string;
  quick_think_llm: string;
  deep_think_llm: string;
  output_language: string;
  checkpoint_enabled: boolean;
  /** Null means "let the server derive from normalized ticker". */
  asset_type: AssetTypeLiteral | null;
}

// ---------------------------------------------------------------------------
// Run snapshot + summary + artifact metadata (run_models.py / schemas.py)
// ---------------------------------------------------------------------------

export type RunStatusLiteral =
  | "created"
  | "running"
  | "cancel_requested"
  | "completed"
  | "failed"
  | "cancelled"
  | "interrupted";

export interface RunSnapshotDTO {
  run_id: string;
  status: RunStatusLiteral;
  ticker: string;
  asset_type: AssetTypeLiteral;
  analysis_date: string;
  selected_analysts: string[];
  max_debate_rounds: number;
  max_risk_discuss_rounds: number;
  output_language: string;
  llm_provider: string;
  quick_think_llm: string;
  deep_think_llm: string;
  configured_keys: Record<string, boolean>;
  created_at: string;
  updated_at: string;
  latest_sequence: number;
  final_signal?: string | null;
  /** Explicit for new completed runs; absent only on legacy snapshots. */
  final_report_artifact_id?: string | null;
  /** Terminal run.completed event time for new completed runs. */
  completed_at?: string | null;
  /** P0 preserves the contract shape; P2 populates normalized entries. */
  degraded_data_sources?: DegradedSourceSummaryDTO[];
  summary?: string | null;
  error_category?: string | null;
  retry_of?: string | null;
  resumed_from_sequence?: number | null;
  /** Opaque resume-fingerprint blob the frontend never interprets. */
  resume_fingerprint?: Record<string, unknown> | null;
  runtime_semantics_hash?: string | null;
  agent_state_schema_sha256?: string | null;
  artifacts: string[];
  redaction_manifest: string[];
  event_schema_version: number;
  /** Opaque server-defined metadata bag. */
  metadata: Record<string, unknown>;
}

export interface DegradedSourceSummaryDTO {
  capability: string;
  status: "degraded" | "unavailable";
  attempted_vendors: string[];
  selected_vendors: string[];
  reasons: Array<{ vendor: string; code: string }>;
  affected_sections: string[];
}

export interface RunSummaryDTO {
  run_id: string;
  status: RunStatusLiteral;
  ticker: string;
  analysis_date: string;
  asset_type: string;
  created_at: string;
  updated_at: string;
  latest_sequence: number;
  final_signal?: string | null;
  summary?: string | null;
}

export interface ArtifactMetadataDTO {
  artifact_id: string;
  kind: string;
  media_type: string;
  content_sha256: string;
  byte_size: number;
  locator: string;
}

// ---------------------------------------------------------------------------
// Error shapes (api.py boundary + schemas.py)
// ---------------------------------------------------------------------------

export interface ApiErrorDetail {
  code: string;
  message: string;
  fields: string[];
  active_run_id?: string;
}

export interface ApiErrorResponse {
  detail: ApiErrorDetail;
}

// ---------------------------------------------------------------------------
// Shared dataclasses (events.py)
// ---------------------------------------------------------------------------

/** Mirror of dataclass ArtifactRef (frozen, validated). */
export interface ArtifactRefDTO {
  artifact_id: string;
  kind: string;
  media_type: string;
  content_sha256: string;
  byte_size: number;
  locator: string;
}

export type ObservationTaskKind = "input" | "role" | "tool" | "maintenance";

/** Mirror of dataclass ObservationCommitV1. node_id/turn_id nullable; tool_call_ids ordered+unique. */
export interface ObservationCommitV1DTO {
  serializer_version: number;
  projection_version: number;
  agent_state_schema_sha256: string;
  task_kind: ObservationTaskKind;
  graph_task_id: string;
  graph_step: number;
  business_delta_sha256: string;
  node_id?: string | null;
  turn_id?: string | null;
  tool_call_ids: string[];
}

// ---------------------------------------------------------------------------
// Event payload variants — one per event type in required_payload_fields().
// Required fields are required keys; optionals are marked with `?`.
// ---------------------------------------------------------------------------

// --- run.* -----------------------------------------------------------------

export interface RunStartedPayload {
  run_status: RunStatusLiteral;
}

/** run.cancel_requested is a non-terminal intermediate state (only run_status). */
export interface RunCancelRequestedPayload {
  run_status: "cancel_requested";
}

export interface RunTerminalPayload {
  run_status: RunStatusLiteral;
  summary?: string | null;
  final_signal?: string | null;
  final_report_artifact_id?: string | null;
  completed_at?: string | null;
  degraded_data_sources?: DegradedSourceSummaryDTO[];
}

export interface RunInterruptedPayload {
  run_status: "interrupted";
  checkpoint_sequence: number;
  summary?: string | null;
}

export interface RunResumedPayload {
  run_status: "running";
  checkpoint_sequence: number;
}

// --- graph.* ---------------------------------------------------------------

export interface GraphTaskStartedPayload {
  graph_task_id: string;
  graph_step: number;
  node_id: string;
}

export interface GraphTaskAbandonedPayload {
  graph_task_id: string;
  graph_step: number;
  node_id: string;
  reason: string;
}

export interface GraphTaskOutputReadyPayload {
  observation_commit: ObservationCommitV1DTO;
  graph_step: number;
  node_id: string;
  business_delta_artifact_id: string;
  media_type: string;
  content_sha256: string;
}

export interface GraphStepAppliedPayload {
  graph_step: number;
  applied_task_ids: string[];
  state_sha256: string;
  next_nodes: string[];
}

export interface GraphCheckpointCommittedPayload {
  graph_step: number;
  applied_task_ids: string[];
  state_sha256: string;
  next_nodes: string[];
  checkpoint_id: string;
}

// --- role.* ----------------------------------------------------------------

export interface RoleStatusChangedPayload {
  role_instance_id: string;
  previous_status: string;
  new_status: string;
  reason: string;
}

// --- agent.* / state.* / report.* ------------------------------------------

export interface AgentMessagePayload {
  turn_id: string;
  graph_task_id: string;
  message_id: string;
  message_kind: string;
}

export interface StateUpdatedPayload {
  turn_id: string;
  changed_keys: string[];
}

export interface ReportUpdatedPayload {
  turn_id: string;
  report_kind: string;
  revision: number;
  artifact_id: string;
}

/**
 * stats.updated has no required keys per required_payload_fields(), but the
 * backend validator requires turn_id OR model_call_id to be present.
 */
export interface StatsUpdatedPayload {
  turn_id?: string;
  model_call_id?: string;
  [key: string]: unknown;
}

// --- turn.* ----------------------------------------------------------------

export interface TurnStartedPayload {
  role_instance_id: string;
  turn_id: string;
  graph_task_id: string;
  graph_step: number;
  turn_index: number;
  turn_status: "started";
}

export interface TurnOutputReadyPayload {
  role_instance_id: string;
  turn_id: string;
  graph_task_id: string;
  graph_step: number;
  turn_index: number;
  turn_status: "output_ready";
  artifact_id: string;
}

export interface TurnEndedPayload {
  role_instance_id: string;
  turn_id: string;
  graph_task_id: string;
  graph_step: number;
  turn_index: number;
  turn_status: "completed" | "failed" | "cancelled" | "interrupted";
  reason: string;
  duration_ms: number;
}

export interface TurnResumedPayload {
  role_instance_id: string;
  turn_id: string;
  graph_task_id: string;
  graph_step: number;
  turn_index: number;
  turn_status: "resumed";
  resumed_from_sequence: number;
}

// --- model.* ---------------------------------------------------------------

export interface ModelUsageDTO {
  /** Opaque token-usage shape; backend-defined. */
  [key: string]: unknown;
}

export interface ModelStartedPayload {
  turn_id: string;
  graph_task_id: string;
  attempt_id: string;
  model_call_id: string;
  provider: string;
  model: string;
  invocation_path: string;
}

export interface ModelEndedPayload {
  turn_id: string;
  graph_task_id: string;
  attempt_id: string;
  model_call_id: string;
  provider: string;
  model: string;
  invocation_path: string;
  duration_ms: number;
  usage: ModelUsageDTO;
}

// --- input.* ---------------------------------------------------------------

export type InputCaptureKind = "state_snapshot" | "config_snapshot" | "prompt_snapshot" | "data_snapshot";

export interface InputSnapshotPayloadBase {
  turn_id: string;
  graph_task_id: string;
  capture_kind: InputCaptureKind;
  artifact_id: string;
  content_sha256: string;
  redaction_manifest: string[];
}

export interface InputStateSnapshotPayload extends InputSnapshotPayloadBase {
  capture_kind: "state_snapshot";
}

export interface InputConfigSnapshotPayload extends InputSnapshotPayloadBase {
  capture_kind: "config_snapshot";
}

export interface InputPromptSnapshotPayload extends InputSnapshotPayloadBase {
  capture_kind: "prompt_snapshot";
  attempt_id: string;
  model_call_id: string;
}

export interface InputDataSnapshotPayload extends InputSnapshotPayloadBase {
  capture_kind: "data_snapshot";
}

// --- tool.* ----------------------------------------------------------------

export interface ToolRequestedPayload {
  turn_id: string;
  graph_task_id: string;
  attempt_id: string;
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
}

export interface ToolExecutionPayloadBase {
  turn_id: string;
  graph_task_id: string;
  attempt_id: string;
  tool_call_id: string;
  tool_name: string;
  tool_execution_id: string;
}

export interface ToolExecutionStartedPayload extends ToolExecutionPayloadBase {}

export interface ToolExecutionCompletedPayload extends ToolExecutionPayloadBase {}

export interface ToolExecutionFailedPayload extends ToolExecutionPayloadBase {}

export interface ToolCommittedPayload {
  turn_id: string;
  graph_task_id: string;
  attempt_id: string;
  tool_call_id: string;
  tool_name: string;
  checkpoint_event_id: string;
}

export interface ToolCancelledPayload {
  turn_id: string;
  graph_task_id: string;
  attempt_id: string;
  tool_call_id: string;
  tool_name: string;
  reason: string;
}

// --- data.* ----------------------------------------------------------------

export interface DataCallPayloadBase {
  turn_id: string;
  graph_task_id: string;
  vendor_call_id: string;
  method: string;
  vendor: string;
  stage: string;
  data_status: string;
  /** Stable non-secret category for failed vendor calls. */
  failure_code?: string;
  fallback_chain?: string[];
}

export interface DataProgressPayload extends DataCallPayloadBase {}

export interface DataCompletedPayload extends DataCallPayloadBase {
  duration_ms: number;
}

export interface DataFailedPayload extends DataCallPayloadBase {
  duration_ms: number;
}

export interface DataInterruptedPayload extends DataCallPayloadBase {
  duration_ms: number;
}

export interface DataCacheHitPayload {
  turn_id: string;
  graph_task_id: string;
  cache_hit_id: string;
  cache_key_sha256: string;
  origin_vendor_call_ids: string[];
  origin_artifacts: ArtifactRefDTO[];
  age_ms: number;
}

// --- artifact.* ------------------------------------------------------------

export interface ArtifactWrittenPayload {
  artifact_id: string;
  kind: string;
  media_type: string;
  content_sha256: string;
  byte_size: number;
  locator: string;
}

// ---------------------------------------------------------------------------
// Discriminated payload union.
//
// Per F2 spec §9.5, event types not enumerated here (future, server-introduced
// types) MUST be ignored by the reducer and never throw. Consumers should
// narrow via the `type` discriminant and fall through for unknown variants.
// ---------------------------------------------------------------------------

/**
 * Union of every event payload the TradingAgents backend can emit today,
 * keyed by the envelope `type`. Unknown future event types are ignored per
 * spec §9.5 — see `UnknownEventType` at the bottom of this section.
 */
export type EventPayloadByType =
  | { type: "run.started"; payload: RunStartedPayload }
  | { type: "run.cancel_requested"; payload: RunCancelRequestedPayload }
  | { type: "run.completed"; payload: RunTerminalPayload }
  | { type: "run.failed"; payload: RunTerminalPayload }
  | { type: "run.cancelled"; payload: RunTerminalPayload }
  | { type: "run.interrupted"; payload: RunInterruptedPayload }
  | { type: "run.resumed"; payload: RunResumedPayload }
  | { type: "graph.task_started"; payload: GraphTaskStartedPayload }
  | { type: "graph.task_abandoned"; payload: GraphTaskAbandonedPayload }
  | { type: "graph.task_output_ready"; payload: GraphTaskOutputReadyPayload }
  | { type: "graph.step_applied"; payload: GraphStepAppliedPayload }
  | { type: "graph.checkpoint_committed"; payload: GraphCheckpointCommittedPayload }
  | { type: "role.status_changed"; payload: RoleStatusChangedPayload }
  | { type: "agent.message"; payload: AgentMessagePayload }
  | { type: "state.updated"; payload: StateUpdatedPayload }
  | { type: "report.updated"; payload: ReportUpdatedPayload }
  | { type: "stats.updated"; payload: StatsUpdatedPayload }
  | { type: "turn.started"; payload: TurnStartedPayload }
  | { type: "turn.output_ready"; payload: TurnOutputReadyPayload }
  | { type: "turn.completed"; payload: TurnEndedPayload }
  | { type: "turn.failed"; payload: TurnEndedPayload }
  | { type: "turn.cancelled"; payload: TurnEndedPayload }
  | { type: "turn.interrupted"; payload: TurnEndedPayload }
  | { type: "turn.resumed"; payload: TurnResumedPayload }
  | { type: "model.started"; payload: ModelStartedPayload }
  | { type: "model.completed"; payload: ModelEndedPayload }
  | { type: "model.failed"; payload: ModelEndedPayload }
  | { type: "input.state_snapshot"; payload: InputStateSnapshotPayload }
  | { type: "input.config_snapshot"; payload: InputConfigSnapshotPayload }
  | { type: "input.prompt_snapshot"; payload: InputPromptSnapshotPayload }
  | { type: "input.data_snapshot"; payload: InputDataSnapshotPayload }
  | { type: "tool.requested"; payload: ToolRequestedPayload }
  | { type: "tool.execution_started"; payload: ToolExecutionStartedPayload }
  | { type: "tool.execution_completed"; payload: ToolExecutionCompletedPayload }
  | { type: "tool.execution_failed"; payload: ToolExecutionFailedPayload }
  | { type: "tool.committed"; payload: ToolCommittedPayload }
  | { type: "tool.cancelled"; payload: ToolCancelledPayload }
  | { type: "data.progress"; payload: DataProgressPayload }
  | { type: "data.completed"; payload: DataCompletedPayload }
  | { type: "data.failed"; payload: DataFailedPayload }
  | { type: "data.interrupted"; payload: DataInterruptedPayload }
  | { type: "data.cache_hit"; payload: DataCacheHitPayload }
  | { type: "artifact.written"; payload: ArtifactWrittenPayload };

/** Any payload shape, without the wrapping `type`. */
export type AnyEventPayload = EventPayloadByType["payload"];

/** Envelope core shared by every persisted event. */
export interface EventEnvelopeCore {
  event_id: string;
  run_id: string;
  sequence: number;
  timestamp: string;
  team_id?: string | null;
  actor_id?: string | null;
  node_id?: string | null;
  status?: string | null;
  parent_event_id?: string | null;
  schema_version: number;
}

/**
 * Loose SSE envelope: `type` is a string and `payload` is an opaque record.
 * Use this for raw transport decoding; narrow to `TypedPersistedEvent` once
 * the `type` is inspected.
 */
export interface PersistedEventDTO extends EventEnvelopeCore {
  type: string;
  payload: Record<string, unknown>;
}

/**
 * Strongly-typed envelope union discriminated on `type`. Unknown future event
 * types are ignored per spec §9.5 — narrow with a `switch` and provide a
 * `default` no-op branch rather than an exhaustive `never` check.
 */
export type TypedPersistedEvent = EventPayloadByType & EventEnvelopeCore;

/** Set of every known event `type` string emitted today. */
export type KnownEventType = EventPayloadByType["type"];

/**
 * Catch-all for server-introduced event types the frontend does not yet know.
 * The reducer receives this shape (loose envelope) and MUST skip it.
 */
export interface UnknownEventType extends EventEnvelopeCore {
  type: string;
  payload: Record<string, unknown>;
}
