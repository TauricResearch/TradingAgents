// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The transport both Tauric clients share. Tauric publishes two documents: the data API, and the
 * applications API (accounts and application storage). One transport sends each request with the key
 * and this build's name, bounds its answer, maps a failure to a DataError, and checks every JSON answer
 * against the pinned part of its document before anything reads it: an answer in a form we do not read
 * is `unavailable`, with where it differs, never a crash.
 *
 * The API key is sent only as a bearer header and appears in no error raised from here.
 */

import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js";
import createClient, { type Client } from "openapi-fetch";
import { message, USER_AGENT } from "../../contracts/index.js";
import { ANSWER_BYTES, CALLS, REQUEST_MS } from "../../contracts/limits.js";
import { bounded } from "../bounded.js";
import { DataError, type DataErrorDetails, type DataErrorKind } from "../errors.js";
import applicationsPinned from "./applications.openapi.json" with { type: "json" };
import type { components as ApplicationComponents } from "./applications.schema.generated.js";
import pinned from "./openapi.json" with { type: "json" };
import type { components } from "./schema.generated.js";

export const TAURIC_BASE_URL = "https://api.tauric.ai";
export const SOURCE = "Tauric";

/** Which published document a route belongs to. */
type Document = "data" | "applications";

/** Per-call options: `signal` cancels the request. */
export type Call = { signal?: AbortSignal };

export const within = (signal?: AbortSignal) => (signal ? { signal } : {});

/** The length a closed byte range asks for, which bounds its answer; undefined for anything else. */
function rangeBytes(range: string | null): number | undefined {
  const match = /^bytes=(\d+)-(\d+)$/.exec(range ?? "");
  return match ? Number(match[2]) - Number(match[1]) + 1 : undefined;
}

export type TransportOptions = {
  apiKey: string;
  baseUrl?: string;
  fetch?: typeof globalThis.fetch;
};

export class TauricTransport {
  private readonly apiKey: string;
  private readonly options: Parameters<typeof createClient>[0];

  constructor({ apiKey, baseUrl = TAURIC_BASE_URL, fetch = globalThis.fetch }: TransportOptions) {
    if (!apiKey) throw new DataError("not_configured", "No Tauric API key is set.", { source: SOURCE });
    this.apiKey = apiKey;
    this.options = {
      baseUrl: baseUrl.replace(/\/+$/, ""),
      headers: { Authorization: `Bearer ${apiKey}`, "User-Agent": USER_AGENT },
      // The caller's signal (on the request) and the client's own timeout, whichever ends first. A
      // range bounds the content it asks for; an error's answer has the general bound.
      fetch: async (request: Request) => {
        const response = await fetch(request, {
          signal: AbortSignal.any([request.signal, AbortSignal.timeout(REQUEST_MS.tauric)]),
        });
        return this.bounded(response, response.ok ? rangeBytes(request.headers.get("Range")) : undefined);
      },
    };
  }

  /** A typed client for one document's routes, over this transport. */
  client<Paths extends {}>(): Client<Paths> {
    return createClient<Paths>(this.options);
  }

  /** One published JSON operation: run it, map a failure, check the answer. */
  async read<T>(
    document: Document,
    method: "get" | "post" | "put" | "patch",
    path: string,
    run: () => Promise<{ data?: T; error?: unknown; response: Response }>,
  ): Promise<T> {
    const { data, error, response } = await this.attempt(run);
    if (error !== undefined || data === undefined) throw this.failure(response, error);
    const validate = responseValidator(document, method, path, response.status);
    if (!validate) {
      throw new DataError(
        "unavailable",
        `Tauric answered ${path} with HTTP ${response.status}, which this version does not read.`,
        {
          source: SOURCE,
          status: response.status,
        },
      );
    }
    if (!validate(data)) throw drift(path, validate);
    return data;
  }

  /** Run one public call; whatever fails leaves as a DataError that never carries the key. */
  async guarded<T>(work: () => Promise<T>): Promise<T> {
    try {
      return await work();
    } catch (cause) {
      const error = cause instanceof DataError ? cause : this.transportFailure(cause);
      const details = Object.fromEntries(
        Object.entries(error.details).map(([key, value]) => [
          key,
          typeof value === "string" ? this.scrub(value) : value,
        ]),
      ) as DataErrorDetails;
      throw new DataError(error.kind, this.scrub(error.message), details);
    }
  }

  /** Run one request; a transport failure leaves as a DataError. */
  async attempt<R>(run: () => Promise<R>): Promise<R> {
    try {
      return await run();
    } catch (cause) {
      throw cause instanceof DataError ? cause : this.transportFailure(cause);
    }
  }

  /** An answer with a status the document does not declare for it. */
  unread(what: string, status: number): DataError {
    return new DataError(
      "unavailable",
      `Tauric answered ${what} with HTTP ${status}, which this version does not read.`,
      {
        source: SOURCE,
        status,
      },
    );
  }

  /** A failed answer as a DataError, judged by the API's own envelope when it is well formed. */
  failure(response: Response, body: unknown): DataError {
    const envelope = (body as { error?: Record<string, unknown> } | null | undefined)?.error;
    // Only a well-formed envelope's code and advice are trusted; anything else is judged by status.
    const error =
      envelope &&
      typeof envelope.code === "string" &&
      envelope.code !== "" &&
      typeof envelope.message === "string" &&
      RETRY_ADVICE.has(String(envelope.retry))
        ? envelope
        : {};
    const code = typeof error.code === "string" ? error.code : undefined;
    const retry = typeof error.retry === "string" ? (error.retry as RetryAdvice) : undefined;
    const status = response.status;
    const message = typeof error.message === "string" ? error.message : `HTTP ${status}`;
    const retryAfter = Number(response.headers.get("Retry-After"));
    const details = {
      source: SOURCE,
      status,
      ...(code ? { code } : {}),
      ...(retry ? { retry } : {}),
      ...(Number.isFinite(retryAfter) && retryAfter >= 0 && response.headers.has("Retry-After")
        ? { retryAfterMs: retryAfter * 1000 }
        : {}),
      ...(typeof error.resets_at === "string" ? { resetsAt: error.resets_at } : {}),
      ...(typeof error.size === "number" ? { size: error.size } : {}),
      ...(typeof error.remaining_bytes === "number" ? { remainingBytes: error.remaining_bytes } : {}),
      ...(Array.isArray(error.candidates) ? { candidates: candidatesOf(error.candidates) } : {}),
    };
    // "Not found" is a fact about the data only when the API itself says it; a bare 404 or 410 (a proxy,
    // a moved route) says nothing about the market.
    const kind =
      error === envelope || (status !== 404 && status !== 410)
        ? failureKind(status, code, retry)
        : "unavailable";
    return new DataError(kind, `Tauric: ${message}`, details);
  }

  /** An answer read only up to `maxBytes`; a longer one is unavailable. */
  private bounded(response: Response, maxBytes = ANSWER_BYTES): Response {
    return bounded(
      response,
      maxBytes,
      () =>
        new DataError("unavailable", message("data.answerTooLong", { source: SOURCE, bytes: maxBytes }), {
          source: SOURCE,
          status: response.status,
        }),
    );
  }

  private transportFailure(cause: unknown): DataError {
    const what = cause instanceof Error ? cause.name : "error";
    const message =
      // A body that does not parse as the JSON it says it is.
      what === "SyntaxError"
        ? "Tauric answered with something other than JSON."
        : what === "TimeoutError"
          ? "Tauric did not answer in time."
          : what === "AbortError"
            ? "The request to Tauric was cancelled."
            : `Tauric could not be reached (${what}).`;
    return new DataError("unavailable", message, { source: SOURCE });
  }

  private scrub(text: string): string {
    return text.replaceAll(this.apiKey, "***");
  }
}

type RetryAdvice = NonNullable<DataErrorDetails["retry"]>;
const RETRY_ADVICE = new Set<string>(["later", "never", "change_request"] satisfies RetryAdvice[]);

type ErrorCode = components["schemas"]["Error"]["code"] | ApplicationComponents["schemas"]["Error"]["code"];

/** The codes the two published documents list. */
const KNOWN_CODES = new Set<string>([
  ...(pinned.components.schemas.Error.properties.code.enum as ErrorCode[]),
  ...(applicationsPinned.components.schemas.Error.properties.code.enum as ErrorCode[]),
]);

/** What this source does not cover, as opposed to what does not exist: another source may have it. */
const UNSUPPORTED = new Set<string>([
  "not_registered",
  "not_supported",
  "not_published",
  "insufficient_history",
] satisfies ErrorCode[]);

const REJECTED = new Set<string>([
  "missing_api_key",
  "invalid_api_key",
  "api_key_inactive",
  "api_key_expired",
  "principal_not_permitted",
  "entitlement_required",
  "account_inactive",
] satisfies ErrorCode[]);

/** How the caller should react, from the answer's code and its own `retry` advice. */
export function failureKind(status: number, code?: string, retry?: string): DataErrorKind {
  if (status >= 500) return "unavailable";
  // Codes are an open set: one this version does not know is a general error, judged by its advice alone
  // (asking again later, or not as it is), never by what its status means for a known code, and never
  // taken for a fact about the market.
  if (code && !KNOWN_CODES.has(code)) return retry === "later" ? "unavailable" : "invalid";
  if (code === "storage_full") return "full";
  if (code === "quota_exhausted") return "quota";
  if (code === "rate_limit_exceeded" || code === "concurrency_limit_reached" || status === 429)
    return "rate_limited";
  if ((code && REJECTED.has(code)) || status === 401 || status === 403) return "rejected";
  if (code === "session_offset_mismatch") return "conflict";
  if (code === "session_diverged") return "diverged";
  // Whatever retry advice comes with it.
  if (code && UNSUPPORTED.has(code)) return "unsupported";
  if (retry === "change_request" || status === 400 || status === 422) return "invalid";
  // Absence is a fact only for an item the source says it does not have, never for "do not retry".
  if (code === "not_found" || code === "gone" || code === "delisted") return "no_data";
  if (status === 404 || status === 410) return "no_data";
  return "unavailable";
}

// Answers are checked against the pinned document, compiled once per schema on first use. Objects
// stay open (the document does not close them), so a field the API adds later passes.
const ajv = new Ajv2020({ strict: false, validateFormats: false, allErrors: false });
ajv.addSchema(pinned as object, "data");
ajv.addSchema(applicationsPinned as object, "applications");
const DOCUMENTS: Record<Document, { paths: unknown }> = { data: pinned, applications: applicationsPinned };
const validators = new Map<string, ValidateFunction | undefined>();

function pointer(...segments: string[]): string {
  return segments.map((s) => s.replaceAll("~", "~0").replaceAll("/", "~1")).join("/");
}

function responseValidator(
  document: Document,
  method: string,
  path: string,
  status: number,
): ValidateFunction | undefined {
  const key = `${document} ${method} ${path} ${status}`;
  if (!validators.has(key)) {
    const responses = (
      DOCUMENTS[document].paths as Record<string, Record<string, { responses?: Record<string, unknown> }>>
    )[path]?.[method]?.responses;
    const declared = responses?.[String(status)] as { content?: Record<string, unknown> } | undefined;
    validators.set(
      key,
      declared?.content?.["application/json"]
        ? ajv.compile({
            $ref: `${document}#/${pointer("paths", path, method, "responses", String(status), "content", "application/json", "schema")}`,
          })
        : undefined,
    );
  }
  return validators.get(key);
}

function drift(where: string, validate: ValidateFunction): DataError {
  const first = validate.errors?.[0];
  const at = first ? `${first.instancePath || "/"} ${first.message ?? ""}`.trim() : "unknown";
  return new DataError(
    "unavailable",
    `Tauric answered ${where} in a form this version does not read (${at}).`,
    {
      source: SOURCE,
    },
  );
}

/** The listings an ambiguous symbol could mean, as the API names them (at most ten). */
function candidatesOf(list: unknown[]): { symbol: string; name: string }[] {
  return list
    .filter((item): item is { symbol: string; name: string } => {
      const candidate = item as { symbol?: unknown; name?: unknown } | null;
      return typeof candidate?.symbol === "string" && typeof candidate.name === "string";
    })
    .slice(0, CALLS.symbolCandidates)
    .map(({ symbol, name }) => ({ symbol, name }));
}
