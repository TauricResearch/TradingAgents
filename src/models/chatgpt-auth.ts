// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Sign in with ChatGPT, so model calls use the person's ChatGPT plan. This follows OpenAI's documented
 * flow for open-source apps (dynamic client registration, PKCE, a loopback redirect on 127.0.0.1), not
 * any first-party client. The sign-in, its tokens and this host's id live in one private file.
 * Refresh tokens rotate, and sending a used one ends the sign-in, so a refresh runs once per process
 * at a time and under a lock shared with other processes, starting from the file as it is then.
 */

import { createHash, createPublicKey, type JsonWebKey, randomBytes, randomUUID, verify } from "node:crypto";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { APP_NAME, APP_TITLE, message } from "../contracts/index.js";
import { REQUEST_MS, SIGN_IN } from "../contracts/limits.js";
import { Lock, readPrivate, writePrivate } from "../store/index.js";
import { OPENAI_API_BASE } from "./hosted.js";

const ISSUER = "https://auth.openai.com";
const AUTHORIZE_URL = `${ISSUER}/api/accounts/authorize`;
const TOKEN_URL = `${ISSUER}/api/accounts/oauth/token`;
const REVOKE_URL = `${ISSUER}/api/accounts/oauth/revoke`;
const JWKS_URL = `${ISSUER}/.well-known/jwks.json`;
const DYNAMIC_CLIENT_ID = "dynamic_agent_client";
/** The command people run (the catalog's sign-in hints name it), and the product's name. */
const NAMES = { app: APP_NAME, product: APP_TITLE };
const SCOPE = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct";
const PLAN_SCOPE = "chatgpt.tokens.use.direct";
const CALLBACK_PATH = "/auth/callback";
const DEFAULT_PORT = 1455;

const SIGN_IN_HINT = message("signin.hint", { app: APP_NAME });

/**
 * Signing in or renewing failed; the message says what to do. `failure` tells a model call how to
 * report it: the sign-in must be redone, or OpenAI may answer later.
 */
export class ChatGPTAuthError extends Error {
  override readonly name: string = "ChatGPTAuthError";
  readonly failure: { kind: "auth" | "provider"; retryable: boolean } = { kind: "auth", retryable: false };
}
/** OpenAI could not be reached or was busy; the sign-in itself may still be good. */
export class ChatGPTUnreachableError extends ChatGPTAuthError {
  override readonly name = "ChatGPTUnreachableError";
  override readonly failure = { kind: "provider" as const, retryable: true };
}
/** OpenAI refused the sign-in's renewal: it has ended, and its tokens are cleared. */
class ChatGPTRefusedError extends ChatGPTAuthError {
  override readonly name = "ChatGPTRefusedError";
}

type Tokens = {
  access_token: string;
  refresh_token?: string;
  /** Seconds since the epoch. */
  expires_at: number;
  earliest_refresh_at?: number | null;
  scopes: string[];
};
type AuthFile = {
  host_id?: string;
  /** The client OpenAI registered for this host, kept from the moment it is issued. */
  registration?: { client_id: string };
  account?: { client_id: string; email?: string; subject: string };
  tokens?: Tokens;
};

type ChatGPTAuthOptions = {
  /** The private file the sign-in is kept in. */
  path: string;
  fetch?: typeof globalThis.fetch;
  /** Seconds since the epoch. */
  now?: () => number;
};

const b64url = (bytes: Buffer) => bytes.toString("base64url");

/** A model the plan offers. */
type PlanModel = { name: string; id: string; contextWindow?: number };

export class ChatGPTAuth {
  private renewing: Promise<string> | undefined;
  private retryAfter = 0;
  private readonly fetchImpl: typeof globalThis.fetch;
  private readonly now: () => number;

  constructor(private readonly options: ChatGPTAuthOptions) {
    this.fetchImpl = options.fetch ?? fetch;
    this.now = options.now ?? (() => Date.now() / 1000);
  }

  /** Whether the plan may be used: signed in, with plan usage approved. */
  async canUsePlan(): Promise<boolean> {
    return (await this.read()).tokens?.scopes.includes(PLAN_SCOPE) ?? false;
  }

  /**
   * A valid access token, renewed when it has under five minutes left, or when the API refused the
   * token given as `rejected` (unless it was already replaced). When OpenAI cannot be reached, a
   * token that still works is used and renewal is tried again a minute later.
   */
  async accessToken({ rejected }: { rejected?: string } = {}): Promise<string> {
    const tokens = (await this.read()).tokens;
    if (!tokens) throw new ChatGPTAuthError(SIGN_IN_HINT);
    requirePlan(tokens);
    if (!needsRenewal(tokens, this.now(), rejected)) return tokens.access_token;
    // One renewal per process at a time; callers wait for it rather than start another.
    this.renewing ??= this.renew(rejected).finally(() => {
      this.renewing = undefined;
    });
    let token: string;
    try {
      token = await this.renewing;
    } catch (error) {
      // A renewal another caller forced could not reach OpenAI; this caller's token still works.
      if (
        rejected === undefined &&
        error instanceof ChatGPTUnreachableError &&
        tokens.expires_at > this.now()
      ) {
        return tokens.access_token;
      }
      throw error;
    }
    // A renewal already under way that kept the token the API refused is no answer to that refusal.
    if (rejected !== undefined && token === rejected) {
      throw new ChatGPTUnreachableError(message("signin.renewFailedNow"));
    }
    return token;
  }

  private async renew(rejected: string | undefined): Promise<string> {
    return this.locked(async () => {
      // The file as it is now: another process may have renewed it already.
      const data = await this.read();
      const tokens = data.tokens;
      if (!tokens || !data.account) throw new ChatGPTAuthError(SIGN_IN_HINT);
      const now = this.now();
      if (!needsRenewal(tokens, now, rejected)) return requirePlan(tokens).access_token;
      const force = rejected !== undefined;
      const stillWorks = tokens.expires_at > now && !force;
      if (now < this.retryAfter) {
        if (stillWorks) return requirePlan(tokens).access_token;
        throw new ChatGPTUnreachableError(message("signin.renewFailedRecently"));
      }
      if (!tokens.refresh_token)
        throw new ChatGPTAuthError(message("signin.cannotRenew", { hint: SIGN_IN_HINT }));
      let renewed: Tokens;
      // Once OpenAI answers, the refresh token on file is used up, whatever happens next.
      let answered = false;
      try {
        const keys = await this.signingKeys();
        const body = await this.tokenRequest(
          {
            grant_type: "refresh_token",
            client_id: data.account.client_id,
            refresh_token: tokens.refresh_token,
            resource: OPENAI_API_BASE,
          },
          message("signin.renewTask"),
          message("signin.signInAgainAction", { app: APP_NAME }),
          () => {
            answered = true;
          },
        );
        if (typeof body.id_token === "string") {
          const claims = this.claims(body.id_token, data.account.client_id, undefined, keys);
          if (claims.sub !== data.account.subject) {
            throw new ChatGPTAuthError(message("signin.otherAccountRenewed"));
          }
        }
        renewed = tokenRecord(body, now, tokens);
      } catch (error) {
        // A refused renewal, or one answered but not kept, ends the sign-in: its tokens are of no further use.
        if (answered || error instanceof ChatGPTRefusedError) {
          const { tokens: _, ...kept } = data;
          await this.write(kept);
          // Trying again cannot help once the sign-in has ended.
          if (error instanceof ChatGPTUnreachableError)
            throw new ChatGPTAuthError(message("signin.renewUnreadable", { app: APP_NAME }));
          throw error;
        }
        if (error instanceof ChatGPTUnreachableError) {
          this.retryAfter = now + SIGN_IN.retryAfterSeconds;
          if (stillWorks) return requirePlan(tokens).access_token;
        }
        throw error;
      }
      // The rotated refresh token must be kept: a failure to write it is reported, never ignored.
      await this.write({ ...data, tokens: renewed });
      // Plan usage can be withdrawn at renewal; the renewed sign-in is kept, but not used for the plan.
      return requirePlan(renewed).access_token;
    });
  }

  /**
   * Sign in and save the result; returns the account's email. `say` shows the address to open; when
   * the browser cannot reach this machine, the address it ends up on can be pasted through `pasted`.
   */
  async signIn({
    say,
    pasted,
    timeoutMs = SIGN_IN.browserMs,
    port = DEFAULT_PORT,
    signal,
  }: {
    say: (text: string) => void;
    pasted?: AsyncIterable<string>;
    timeoutMs?: number;
    port?: number;
    /** Stops the sign-in: its callback address closes and it fails as cancelled. */
    signal?: AbortSignal;
  }): Promise<string> {
    // This host's id is kept before anything else, so a sign-in that fails keeps the same id next time;
    // it is chosen under the lock, so two first sign-ins agree on it.
    const data = await this.locked(async () => {
      const current = await this.read();
      if (current.host_id) return current;
      const next = { ...current, host_id: `urn:uuid:${randomUUID()}` };
      await this.write(next);
      return next;
    });
    const hostId = data.host_id as string;
    const account = data.account;
    const clientId = account?.client_id ?? data.registration?.client_id ?? DYNAMIC_CLIENT_ID;
    const state = b64url(randomBytes(32));
    const nonce = b64url(randomBytes(32));
    const verifier = b64url(randomBytes(64));
    let redirectUri = "";
    const answer = await new Promise<URLSearchParams>((resolve, reject) => {
      let server: Server | undefined;
      const timer = setTimeout(
        () => finish(new ChatGPTAuthError(message("signin.timedOut", { app: APP_NAME }))),
        timeoutMs,
      );
      timer.unref?.();
      const cancelled = () => finish(new ChatGPTAuthError(message("signin.cancelled")));
      const finish = (result: URLSearchParams | Error) => {
        clearTimeout(timer);
        signal?.removeEventListener("abort", cancelled);
        const closing = server;
        closing?.close();
        closing?.closeIdleConnections();
        // The callback's own answer is still being written; then a connection left open (a request never
        // finished) must not keep this process.
        setTimeout(() => closing?.closeAllConnections(), SIGN_IN.callbackCloseMs).unref();
        if (result instanceof Error) reject(result);
        else resolve(result);
      };
      const accept = (address: string) => {
        let url: URL;
        try {
          url = new URL(address.trim(), "http://127.0.0.1");
        } catch {
          return false;
        }
        if (url.pathname !== CALLBACK_PATH || url.searchParams.get("state") !== state) return false;
        finish(url.searchParams);
        return true;
      };
      const handler = (request: IncomingMessage, response: ServerResponse) => {
        const ok = accept(request.url ?? "");
        response.writeHead(ok ? 200 : 400, { "Content-Type": "text/plain; charset=utf-8" });
        response.end(ok ? `${message("signin.returnToTerminal", { product: APP_TITLE })}\n` : "");
      };
      const listening = (actual: number) => {
        const redirect = `http://127.0.0.1:${actual}${CALLBACK_PATH}`;
        redirectUri = redirect;
        const params = new URLSearchParams({
          client_id: clientId,
          ext_agent_host_id: hostId,
          response_type: "code",
          redirect_uri: redirect,
          scope: SCOPE,
          resource: OPENAI_API_BASE,
          state,
          nonce,
          code_challenge_method: "S256",
          code_challenge: b64url(createHash("sha256").update(verifier).digest()),
        });
        if (clientId === DYNAMIC_CLIENT_ID) params.set("agent_name_hint", APP_TITLE);
        else if (account?.email) params.set("login_hint", account.email);
        const url = `${AUTHORIZE_URL}?${params}`;
        say(message("signin.openAddress"));
        say(url);
        say(message("signin.pasteIfNeeded"));
        if (pasted) {
          void (async () => {
            for await (const line of pasted) {
              if (accept(line)) return;
              say(message("signin.notThatAddress"));
            }
          })();
        }
      };
      server = createServer(handler);
      server.once("error", () => {
        // The usual port is taken: any free one will do.
        const fallback = createServer(handler);
        server = fallback;
        fallback.once("error", (error: NodeJS.ErrnoException) =>
          finish(new ChatGPTAuthError(message("signin.cannotListen", { reason: error.code ?? error.name }))),
        );
        fallback.listen(0, "127.0.0.1", () => listening((fallback.address() as { port: number }).port));
      });
      const first = server;
      first.listen(port, "127.0.0.1", () => listening((first.address() as { port: number }).port));
      if (signal?.aborted) cancelled();
      else signal?.addEventListener("abort", cancelled, { once: true });
    });

    const refused = answer.get("error");
    if (refused !== null) {
      const code = oauthError({ error: refused });
      throw new ChatGPTAuthError(message("signin.notCompleted", code ? { code } : {}));
    }
    const issued = answer.get("client_id") ?? clientId;
    if (issued === DYNAMIC_CLIENT_ID || (account?.client_id && issued !== account.client_id)) {
      throw new ChatGPTAuthError(message("signin.notRegistered", NAMES));
    }
    // The registration is kept before the code is exchanged, so a failed exchange is retried with it.
    if (issued !== data.registration?.client_id) {
      await this.locked(async () =>
        this.write({ ...(await this.read()), registration: { client_id: issued } }),
      );
    }
    const keys = await this.signingKeys();
    const body = await this.tokenRequest(
      {
        grant_type: "authorization_code",
        client_id: issued,
        code: answer.get("code") ?? "",
        code_verifier: verifier,
        redirect_uri: redirectUri,
        resource: OPENAI_API_BASE,
      },
      message("signin.signInTask"),
      message("signin.signInAgain"),
    );
    const claims = this.claims(typeof body.id_token === "string" ? body.id_token : "", issued, nonce, keys);
    if (account?.subject && claims.sub !== account.subject) {
      throw new ChatGPTAuthError(
        message("signin.otherAccount", { app: APP_NAME, ...(account.email ? { email: account.email } : {}) }),
      );
    }
    const tokens = tokenRecord(body, this.now());
    const replaced = await this.locked(async () => {
      const current = await this.read();
      await this.write({
        host_id: hostId,
        registration: { client_id: issued },
        account: { client_id: issued, subject: claims.sub, ...(claims.email ? { email: claims.email } : {}) },
        tokens,
      });
      return current.tokens;
    });
    if (replaced?.refresh_token) await this.revoke(replaced.refresh_token, issued);
    // Signed in without plan usage approved: the identity is kept, but the plan cannot be used.
    if (!tokens.scopes.includes(PLAN_SCOPE)) {
      throw new ChatGPTAuthError(message("signin.planDenied", NAMES));
    }
    return claims.email ?? message("signin.yourAccount");
  }

  /**
   * Revoke the sign-in at OpenAI and clear its tokens, keeping this host's id and the registration.
   * Says whether OpenAI confirmed the revocation.
   */
  async signOut(): Promise<"revoked" | "forgotten" | undefined> {
    return this.locked(async () => {
      const data = await this.read();
      if (!data.tokens) return undefined;
      const revoked = data.tokens.refresh_token
        ? await this.revoke(data.tokens.refresh_token, data.account?.client_id)
        : false;
      const { tokens: _, ...kept } = data;
      await this.write(kept);
      return revoked ? "revoked" : "forgotten";
    });
  }

  /** The models the plan offers, in OpenAI's order, with the context window each reports. */
  async models(timeoutMs: number = REQUEST_MS.signIn): Promise<PlanModel[]> {
    const response = await this.fetchImpl(`${OPENAI_API_BASE}/models`, {
      headers: { Authorization: `Bearer ${await this.accessToken()}` },
      redirect: "error",
      signal: AbortSignal.timeout(timeoutMs),
    });
    // A refused sign-in must be redone; any other failure may pass.
    if (response.status === 401 || response.status === 403) {
      const action = message("signin.signInAgainAction", { app: APP_NAME });
      throw new ChatGPTAuthError(
        message("signin.refused", {
          task: message("signin.modelsTask"),
          code: `HTTP ${response.status}`,
          action,
        }),
      );
    }
    if (!response.ok)
      throw new ChatGPTUnreachableError(message("signin.modelsUnlisted", { status: response.status }));
    const body = (await response.json()) as { models?: unknown[] };
    return (body.models ?? [])
      .filter(
        (
          m,
        ): m is {
          slug: string;
          display_name?: string;
          visibility?: string;
          supported_in_api?: boolean;
          priority?: number;
          context_window?: unknown;
        } => typeof m === "object" && m !== null && typeof (m as { slug?: unknown }).slug === "string",
      )
      .filter((m) => m.visibility === "list" && m.supported_in_api !== false)
      .sort((a, b) => (a.priority ?? 0) - (b.priority ?? 0))
      .map((m) => ({
        name: m.display_name ?? m.slug,
        id: m.slug,
        ...(Number.isInteger(m.context_window) && (m.context_window as number) > 0
          ? { contextWindow: m.context_window as number }
          : {}),
      }));
  }

  /** OpenAI's signing keys; none fetched means OpenAI cannot be checked, so nothing is sent. */
  private async signingKeys(): Promise<JsonWebKey[]> {
    let keys: unknown;
    try {
      const response = await this.fetchImpl(JWKS_URL, {
        redirect: "error",
        signal: AbortSignal.timeout(REQUEST_MS.signIn),
      });
      keys = response.ok ? ((await response.json()) as { keys?: unknown }).keys : undefined;
    } catch {
      keys = undefined;
    }
    // Only keys a signature can be checked with count.
    const usable = (Array.isArray(keys) ? (keys as JsonWebKey[]) : []).filter(
      (key) =>
        key.kty === "RSA" &&
        typeof (key as { kid?: unknown }).kid === "string" &&
        typeof key.n === "string" &&
        typeof key.e === "string",
    );
    if (!usable.length) {
      throw new ChatGPTUnreachableError(message("signin.cannotCheck"));
    }
    return usable;
  }

  /** The id token's claims after checking its RS256 signature, issuer, audience, expiry and nonce. */
  private claims(idToken: string, clientId: string, nonce: string | undefined, keys: JsonWebKey[]) {
    const unverified = new ChatGPTAuthError(message("signin.tokenUnverified"));
    const parts = idToken.split(".");
    if (parts.length !== 3) throw unverified;
    const [headerPart, payloadPart, signaturePart] = parts as [string, string, string];
    let header: { alg?: string; kid?: string };
    let claims: Record<string, unknown>;
    try {
      header = JSON.parse(Buffer.from(headerPart, "base64url").toString("utf8"));
      claims = JSON.parse(Buffer.from(payloadPart, "base64url").toString("utf8"));
    } catch {
      throw unverified;
    }
    const jwk = keys.find((key) => (key as { kid?: string }).kid === header.kid && key.kty === "RSA");
    if (header.alg !== "RS256" || !jwk) throw unverified;
    let valid = false;
    try {
      valid = verify(
        "RSA-SHA256",
        Buffer.from(`${headerPart}.${payloadPart}`),
        createPublicKey({ key: jwk, format: "jwk" }),
        Buffer.from(signaturePart, "base64url"),
      );
    } catch {
      valid = false;
    }
    if (!valid) throw unverified;
    const { iss, aud, sub, exp, email } = claims;
    const audiences = Array.isArray(aud) ? aud : [aud];
    if (
      iss !== ISSUER ||
      !audiences.includes(clientId) ||
      typeof sub !== "string" ||
      !sub ||
      typeof exp !== "number" ||
      !Number.isFinite(exp) ||
      exp + SIGN_IN.clockLeewaySeconds < this.now() ||
      (nonce !== undefined && claims.nonce !== nonce)
    ) {
      throw new ChatGPTAuthError(message("signin.tokenMismatch"));
    }
    return { sub, ...(typeof email === "string" ? { email } : {}) };
  }

  /** OpenAI's answer to a token request; never logs or echoes the form. */
  private async tokenRequest(
    form: Record<string, string>,
    task: string,
    refused: string,
    // Called once OpenAI has accepted the request, before its answer is read.
    accepted?: () => void,
  ): Promise<Record<string, unknown>> {
    let response: Response;
    try {
      response = await this.fetchImpl(TOKEN_URL, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams(form),
        // Credentials go to OpenAI's own endpoint only, never on to wherever an answer points.
        redirect: "error",
        signal: AbortSignal.timeout(REQUEST_MS.signIn),
      });
    } catch {
      throw new ChatGPTUnreachableError(message("signin.unreachable", { task }));
    }
    if (response.status === 200) accepted?.();
    const body = (await response.json().catch(() => undefined)) as Record<string, unknown> | undefined;
    const code = oauthError(body) ?? `HTTP ${response.status}`;
    if (response.status === 408 || response.status === 429 || response.status >= 500) {
      throw new ChatGPTUnreachableError(message("signin.busy", { task, code }));
    }
    if (response.status !== 200)
      throw new ChatGPTRefusedError(message("signin.refused", { task, code, action: refused }));
    if (!body || typeof body.access_token !== "string") {
      throw new ChatGPTUnreachableError(message("signin.unreadable", { task }));
    }
    return body;
  }

  private async revoke(refreshToken: string, clientId: string | undefined): Promise<boolean> {
    try {
      const response = await this.fetchImpl(REVOKE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          token: refreshToken,
          token_type_hint: "refresh_token",
          ...(clientId ? { client_id: clientId } : {}),
        }),
        redirect: "error",
        signal: AbortSignal.timeout(REQUEST_MS.signIn),
      });
      return response.status === 200;
    } catch {
      return false;
    }
  }

  private async read(): Promise<AuthFile> {
    const text = await readPrivate(this.options.path);
    if (!text) return {};
    try {
      const value = JSON.parse(text);
      return typeof value === "object" && value !== null ? (value as AuthFile) : {};
    } catch {
      return {};
    }
  }

  private async write(data: AuthFile): Promise<void> {
    await writePrivate(this.options.path, JSON.stringify(data));
  }

  /** Run `work` holding the sign-in's lock, waiting for another process; never runs it without the lock. */
  private async locked<T>(work: () => Promise<T>): Promise<T> {
    const path = `${this.options.path}.lock`;
    const deadline = Date.now() + SIGN_IN.lockWaitMs;
    let lock = await Lock.acquire(path);
    while (!(lock instanceof Lock)) {
      if (lock.stuck) {
        throw new ChatGPTAuthError(message("signin.lockStuck", { path: lock.stuck }));
      }
      if (Date.now() > deadline) {
        throw new ChatGPTUnreachableError(message("signin.lockBusy", { product: APP_TITLE }));
      }
      await new Promise((resolve) => setTimeout(resolve, SIGN_IN.lockPollMs));
      lock = await Lock.acquire(path);
    }
    try {
      return await work();
    } finally {
      await lock.release();
    }
  }
}

/** The tokens, when the plan may be used with them; signed in without plan approval, no model call may use them. */
function requirePlan(tokens: Tokens): Tokens {
  if (!tokens.scopes.includes(PLAN_SCOPE)) {
    throw new ChatGPTAuthError(message("signin.planNotAllowed", NAMES));
  }
  return tokens;
}

/** Renew when due, or when the API refused the token still on file. */
function needsRenewal(tokens: Tokens, now: number, rejected: string | undefined): boolean {
  return rejected === tokens.access_token || due(tokens, now);
}

/** Whether to renew: under five minutes left and OpenAI accepts a renewal by now, or already expired. */
function due(tokens: Tokens, now: number): boolean {
  if (now < tokens.expires_at - SIGN_IN.refreshMarginSeconds) return false;
  const earliest = tokens.earliest_refresh_at;
  return now >= tokens.expires_at || typeof earliest !== "number" || now >= earliest;
}

function tokenRecord(body: Record<string, unknown>, now: number, previous?: Tokens): Tokens {
  // An answer without `scope` keeps the granted scopes; one with it, even empty, replaces them.
  const scopes =
    typeof body.scope === "string"
      ? body.scope.split(/\s+/).filter(Boolean).sort()
      : (previous?.scopes ?? []);
  return {
    access_token: body.access_token as string,
    ...(typeof body.refresh_token === "string"
      ? { refresh_token: body.refresh_token }
      : previous?.refresh_token
        ? { refresh_token: previous.refresh_token }
        : {}),
    expires_at: now + (typeof body.expires_in === "number" ? body.expires_in : SIGN_IN.assumedTokenSeconds),
    earliest_refresh_at: typeof body.earliest_refresh_at === "number" ? body.earliest_refresh_at : null,
    scopes,
  };
}

/** The standard OAuth error codes, the only part of an error answer repeated (free text may hold a token). */
const OAUTH_ERRORS = new Set([
  "invalid_request",
  "invalid_client",
  "invalid_grant",
  "unauthorized_client",
  "unsupported_grant_type",
  "invalid_scope",
  "access_denied",
  "server_error",
  "temporarily_unavailable",
]);

function oauthError(body: Record<string, unknown> | undefined): string | undefined {
  const error = body?.error;
  const code = typeof error === "string" ? error : (error as { code?: unknown } | undefined)?.code;
  return typeof code === "string" && OAUTH_ERRORS.has(code) ? code : undefined;
}
