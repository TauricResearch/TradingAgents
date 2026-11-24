// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The Tauric applications client: the account, and one application's stored sessions. Requests and
 * answers are typed from the pinned part of the applications document (applications.schema.generated.ts
 * from applications.openapi.json); the shared transport checks each answer against it.
 */

import type { Client } from "openapi-fetch";
import { DataError } from "../errors.js";
import type { components, operations, paths } from "./applications.schema.generated.js";
import { type Call, SOURCE, TauricTransport, type TransportOptions, within } from "./transport.js";

type Schemas = components["schemas"];
type Query<Id extends keyof operations> = NonNullable<operations[Id]["parameters"]["query"]>;

type Account = Schemas["AccountView"];
type ApplicationSession = Schemas["ApplicationSessionView"];
type ApplicationSessionList = Schemas["ApplicationSessionList"];

type TauricApplicationsOptions = TransportOptions & {
  /** The application whose sessions this client reads and writes. */
  application: string;
};

export class TauricApplications {
  private readonly transport: TauricTransport;
  private readonly apps: Client<paths>;
  readonly application: string;

  constructor({ application, ...options }: TauricApplicationsOptions) {
    this.transport = new TauricTransport(options);
    this.apps = this.transport.client<paths>();
    this.application = application;
  }

  /** The account: its tier, pools and storage. */
  account({ signal }: Call = {}): Promise<Account> {
    return this.transport.guarded(() =>
      this.transport.read("applications", "get", "/v1/account", () =>
        this.apps.GET("/v1/account", { ...within(signal) }),
      ),
    );
  }

  listSessions(
    query: Query<"list_application_sessions"> = {},
    { signal }: Call = {},
  ): Promise<ApplicationSessionList> {
    const application = this.application;
    return this.transport.guarded(() =>
      this.transport.read("applications", "get", "/v1/applications/{application}/sessions", () =>
        this.apps.GET("/v1/applications/{application}/sessions", {
          params: { path: { application }, query },
          ...within(signal),
        }),
      ),
    );
  }

  session(sessionId: string, { signal }: Call = {}): Promise<ApplicationSession> {
    const path = this.sessionPath(sessionId);
    return this.transport.guarded(() =>
      this.transport.read("applications", "get", "/v1/applications/{application}/sessions/{session_id}", () =>
        this.apps.GET("/v1/applications/{application}/sessions/{session_id}", {
          params: { path },
          ...within(signal),
        }),
      ),
    );
  }

  /** The stored bytes from `start` to `end` inclusive, or to the end when `end` is omitted. */
  readSession(sessionId: string, start = 0, end?: number, { signal }: Call = {}): Promise<Uint8Array> {
    return this.transport.guarded(() => this.readContent(sessionId, start, end, signal));
  }

  private async readContent(
    sessionId: string,
    start: number,
    end: number | undefined,
    signal: AbortSignal | undefined,
  ): Promise<Uint8Array> {
    const { data, error, response } = await this.transport.attempt(() =>
      this.apps.GET("/v1/applications/{application}/sessions/{session_id}/content", {
        params: { path: this.sessionPath(sessionId) },
        headers: { Range: `bytes=${start}-${end ?? ""}` },
        parseAs: "arrayBuffer",
        ...within(signal),
      }),
    );
    if (error !== undefined || !response.ok) throw this.transport.failure(response, error);
    // The whole content, or the range asked for starting where it was asked.
    const range = /^bytes (\d+)-/.exec(response.headers.get("Content-Range") ?? "");
    if (!(response.status === 200 || (response.status === 206 && Number(range?.[1]) === start))) {
      throw this.transport.unread("content", response.status);
    }
    // An empty range comes back without a body.
    return new Uint8Array(data ?? new ArrayBuffer(0));
  }

  /** Delete the session; repeatable, also for an id never written. */
  deleteSession(sessionId: string): Promise<void> {
    return this.transport.guarded(async () => {
      const { error, response } = await this.transport.attempt(() =>
        this.apps.DELETE("/v1/applications/{application}/sessions/{session_id}", {
          params: { path: this.sessionPath(sessionId) },
        }),
      );
      if (error !== undefined || !response.ok) throw this.transport.failure(response, error);
      if (response.status !== 204) throw this.transport.unread("a delete", response.status);
    });
  }

  /** Create the session, or replace its metadata whole. */
  putSession(
    sessionId: string,
    metadata: Record<string, string>,
    { signal }: Call = {},
  ): Promise<ApplicationSession> {
    return this.transport.guarded(() =>
      this.transport.read("applications", "put", "/v1/applications/{application}/sessions/{session_id}", () =>
        this.apps.PUT("/v1/applications/{application}/sessions/{session_id}", {
          params: { path: this.sessionPath(sessionId) },
          body: { metadata, parent: null },
          ...within(signal),
        }),
      ),
    );
  }

  /**
   * Append whole JSONL lines at `offset`, the session's current size; returns the new size. Sending
   * the same lines at the same offset again is safe: Tauric keeps one copy.
   */
  append(
    sessionId: string,
    offset: number,
    lines: string,
    { signal }: Call = {},
  ): Promise<{ size: number; verifiedTo: number }> {
    return this.transport.guarded(() => this.appendLines(sessionId, offset, lines, signal));
  }

  private async appendLines(
    sessionId: string,
    offset: number,
    lines: string,
    signal: AbortSignal | undefined,
  ): Promise<{ size: number; verifiedTo: number }> {
    // Tauric stores a partial line as given, so a later append would continue it.
    if (!lines.endsWith("\n")) {
      throw new DataError("invalid", "A session append must end with a complete line.", { source: SOURCE });
    }
    const { size, verified_to: verifiedTo } = await this.transport.read(
      "applications",
      "patch",
      "/v1/applications/{application}/sessions/{session_id}/content",
      () =>
        this.apps.PATCH("/v1/applications/{application}/sessions/{session_id}/content", {
          params: { path: this.sessionPath(sessionId) },
          // The bytes go as they are, at the offset they continue from.
          headers: { "Upload-Offset": String(offset), "Content-Type": "application/octet-stream" },
          body: lines,
          bodySerializer: (body: string) => body,
          ...within(signal),
        }),
    );
    // The confirmed cursor is the offset plus the bytes sent; the session may already hold more.
    if (verifiedTo !== offset + new TextEncoder().encode(lines).length || size < verifiedTo) {
      throw new DataError("unavailable", "Tauric answered an append in a form this version does not read.", {
        source: SOURCE,
      });
    }
    return { size, verifiedTo };
  }

  private sessionPath(sessionId: string): { application: string; session_id: string } {
    return { application: this.application, session_id: sessionId };
  }
}
