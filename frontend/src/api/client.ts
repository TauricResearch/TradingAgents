/**
 * F2 - Typed HTTP client for the TradingAgents localhost workbench API.
 *
 * Same-origin: the SPA is served by the FastAPI app itself, so API_BASE is "".
 * All non-2xx responses are parsed into ApiError per the backend's
 * {detail:{code,message,fields,active_run_id?}} error envelope
 * (tradingagents/web/api.py _error_response).
 *
 * No `any`: the only non-typed boundary is fetch()'s Response body, which is
 * decoded via explicit type assertions on the parsed JSON.
 */
import type {
  ApiErrorResponse,
  ArtifactMetadataDTO,
  ConfigResponseDTO,
  MarketEventDTO,
  MarketEventLayer2DTO,
  MarketViewDTO,
  RunCreateRequestDTO,
  RunSnapshotDTO,
  RunSummaryDTO,
} from "./contracts";
import { API } from "./contracts";

/** Same-origin base; prepended to every API path. */
export const API_BASE = "";

/**
 * The F2 spec names this type ConfigPayload, but contracts.ts only exports
 * ConfigResponseDTO (the wire shape). Alias to avoid renaming the wire type.
 */
export type ConfigPayload = ConfigResponseDTO;

/**
 * Defense-in-depth path guard. The backend also validates run_id via
 * RUN_ID_PATTERN in run_models.py; we reject before interpolation so a
 * malformed id can never reach the URL builder.
 */
const SAFE_RUN_ID = /^[A-Za-z0-9_-]+$/;

function assertRunId(run_id: string): void {
  if (!SAFE_RUN_ID.test(run_id)) {
    throw new RangeError(`Refusing to interpolate invalid run_id: ${run_id}`);
  }

}

/**
 * Error thrown for every non-2xx response. Mirrors ApiErrorDetail from
 * contracts.ts. Fields are readonly: errors are values to be inspected, not
 * mutated.
 */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly fields: string[];
  readonly active_run_id?: string;

  constructor(params: {
    code: string;
    message: string;
    status: number;
    fields?: string[];
    active_run_id?: string;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.code = params.code;
    this.status = params.status;
    this.fields = params.fields ?? [];
    this.active_run_id = params.active_run_id;
  }
}

/**
 * Parse a non-2xx Response into an ApiError using the backend error envelope.
 * If the body is not JSON or does not match {detail:{code,message,...}}, fall
 * back to a generic http_error so callers always get an ApiError.
 */
async function toApiError(resp: Response): Promise<ApiError> {
  let envelope: ApiErrorResponse | null = null;
  try {
    envelope = (await resp.json()) as ApiErrorResponse;
  } catch {
    // Body was not JSON (e.g. proxy 502); fall through to generic error.
  }
  const detail = envelope?.detail;
  if (
    detail &&
    typeof detail.code === "string" &&
    typeof detail.message === "string"
  ) {
    return new ApiError({
      code: detail.code,
      message: detail.message,
      status: resp.status,
      fields: Array.isArray(detail.fields) ? detail.fields : [],
      active_run_id: detail.active_run_id,
    });
  }
  return new ApiError({
    code: "http_error",
    message: `HTTP ${resp.status}`,
    status: resp.status,
  });
}

/**
 * Core JSON request helper. Sets JSON headers, parses the backend error
 * envelope on non-2xx into ApiError, and returns decoded JSON on success.
 * Private to this module; raw-bytes callers use readArtifact directly.
 */
async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    throw await toApiError(resp);
  }
  return (await resp.json()) as T;
}

/** GET /api/config */
export function getConfig(): Promise<ConfigPayload> {
  return request<ConfigPayload>("GET", API.config);
}

/** GET /api/runs */
export function listRuns(): Promise<RunSummaryDTO[]> {
  return request<RunSummaryDTO[]>("GET", API.runs);
}

/** GET /api/runs/{run_id} */
export function getRun(run_id: string): Promise<RunSnapshotDTO> {
  assertRunId(run_id);
  return request<RunSnapshotDTO>("GET", API.run(run_id));
}

/**
 * POST /api/runs (201). Throws ApiError on 409 (active_run_conflict) or 422
 * (validation_error / unsupported_provider / missing_configuration / etc.).
 */
export function createRun(body: RunCreateRequestDTO): Promise<RunSnapshotDTO> {
  return request<RunSnapshotDTO>("POST", API.runs, body);
}

/** POST /api/runs/{run_id}/cancel (202). Throws ApiError on 409 run_not_active. */
export function cancelRun(run_id: string): Promise<RunSnapshotDTO> {
  assertRunId(run_id);
  return request<RunSnapshotDTO>("POST", API.cancel(run_id));
}

/** POST /api/runs/{run_id}/retry (201). Throws ApiError on 409 run_not_retryable. */
export function retryRun(run_id: string): Promise<RunSnapshotDTO> {
  assertRunId(run_id);
  return request<RunSnapshotDTO>("POST", API.retry(run_id));
}

/** POST /api/runs/{run_id}/resume (202). Throws ApiError on 409 run_not_resumable / resume_conflict. */
export function resumeRun(run_id: string): Promise<RunSnapshotDTO> {
  assertRunId(run_id);
  return request<RunSnapshotDTO>("POST", API.resume(run_id));
}

/** GET /api/runs/{run_id}/artifacts */
export function listArtifacts(
  run_id: string,
): Promise<ArtifactMetadataDTO[]> {
  assertRunId(run_id);
  return request<ArtifactMetadataDTO[]>("GET", API.artifacts(run_id));
}

/**
 * GET the run's local chart projection.  The server only reads artifacts that
 * were already captured by this run; it never issues a new market-data call.
 * The sequence version gives browser caches a new immutable-ish key as the
 * append-only event log grows.
 */
export function getMarketView(
  run_id: string,
  sequence?: number,
): Promise<MarketViewDTO> {
  assertRunId(run_id);
  return request<MarketViewDTO>("GET", API.marketView(run_id, sequence));
}

/**
 * Read an already-cached public Layer 2 conclusion for one marker.  The
 * server intentionally does not invoke a data vendor or model on cache miss.
 */
export function getMarketEventLayer2(
  run_id: string,
  event: Pick<MarketEventDTO, "artifact_id" | "timestamp" | "title">,
): Promise<MarketEventLayer2DTO> {
  assertRunId(run_id);
  return request<MarketEventLayer2DTO>("GET", API.marketEventLayer2(run_id, event));
}

/**
 * GET /api/runs/{run_id}/artifacts/{artifact_id} (raw bytes).
 * Returns the binary content and the Content-Type header the server attached.
 * artifact_id is encodeURIComponent'd rather than regex-validated because the
 * backend artifact_id space is opaque (store-generated) and may include dots.
 */
export async function readArtifact(
  run_id: string,
  artifact_id: string,
): Promise<{ content: ArrayBuffer; media_type: string }> {
  assertRunId(run_id);
  if (!artifact_id) {
    throw new RangeError("artifact_id must not be empty");
  }
  const path = API.artifact(run_id, encodeURIComponent(artifact_id));
  const resp = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    headers: { Accept: "*/*" },
  });
  if (!resp.ok) {
    throw await toApiError(resp);
  }
  const content = await resp.arrayBuffer();
  const media_type =
    resp.headers.get("Content-Type") ?? "application/octet-stream";
  return { content, media_type };
}

/** Convenience: decode the artifact body as UTF-8 text. */
export async function readArtifactText(
  run_id: string,
  artifact_id: string,
): Promise<string> {
  const { content } = await readArtifact(run_id, artifact_id);
  return new TextDecoder("utf-8").decode(content);
}
