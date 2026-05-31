# Sign in with ChatGPT — `openai-oauth` provider

This provider lets users authenticate with their **ChatGPT** subscription
(Free/Plus/Pro) using the same OAuth flow as the OpenAI Codex CLI, instead of an
`OPENAI_API_KEY`. Model calls are routed through the ChatGPT **Codex backend**
(`https://chatgpt.com/backend-api/codex`) so they draw on the ChatGPT plan.

> ⚠️ **Community / unofficial.** This reuses Codex's public OAuth client and an
> undocumented backend that can change without notice. Whether using it from a
> non-Codex application complies with OpenAI's Terms is the user's
> responsibility. Everything here was reconstructed from the open-source
> `openai/codex` client and verified against the live backend.

## Usage

```bash
tradingagents login      # browser OAuth (Sign in with ChatGPT)
tradingagents            # pick "OpenAI (ChatGPT OAuth)" as the provider
```

Tokens are stored in `~/.tradingagents/oauth_openai.json` (mode `0600`) and
refreshed automatically. Override the path with `TRADINGAGENTS_OAUTH_PATH`.

### Available models depend on the plan
Only Codex-catalog models are accepted by the backend; generic API model IDs
(`gpt-4.1`, `gpt-5`, `*-mini`/`*-nano`) are rejected with HTTP 400
`"... not supported when using Codex with a ChatGPT account."`. `gpt-5.4-mini`
and `gpt-5.5` work broadly (incl. the free plan); `gpt-5.3-codex`, `gpt-5.4`,
`gpt-5.2` require Plus/Pro.

**The CLI auto-discovers the models your account can actually use** so the
dropdown only offers valid choices (`oauth/models.py`). It first queries
`GET .../codex/models?client_version=...`; that endpoint is authoritative for
Plus/Pro but returns an empty list on the free plan, so as a fallback it probes
the catalog candidates with a minimal `/responses` request (concurrent, ~1–2s)
and keeps the ones that return 200. The result is cached per account in
`~/.tradingagents/oauth_models.json` (24h TTL, refreshed on `tradingagents
login`). If discovery fails (e.g. offline), the full catalog is shown.

## Architecture

| Concern | Where | Notes |
|---|---|---|
| OAuth PKCE login + local callback (`:1455`, fallback `:1457`) | `oauth/flow.py` | S256, CSRF `state` check |
| Token persistence + refresh | `oauth/store.py` | expiry from JWT `exp` claim; refresh body is **JSON**; refresh-token rotation; 0600 via `mkstemp` |
| Bearer injection + 401 refresh/retry | `oauth/auth.py` (`httpx.Auth`) | fresh token per request |
| OAuth constants / authorize URL | `oauth/pkce.py` | client `app_EMoamEEZ73f0CkXaXp7hrann`, scope incl. `api.connectors.*` |
| Responses payload rewrite | `oauth/payload.py` + `CodexChatOpenAI` | see below |
| Provider wiring | `factory.py`, `api_key_env.py`, `model_catalog.py`, `openai_client.py` | |
| CLI | `cli/utils.py`, `cli/main.py` | dropdown entry, auto-login, `login` command |

## Codex backend constraints (and how we satisfy them)

The backend rejects standard langchain Responses requests until the body is
adapted. These were each confirmed against the live endpoint:

1. **`store` must be `false`**, **`stream` must be `true`** — else HTTP 400.
   Set as native langchain params (`store=False`, `streaming=True`) and enforced
   again in the payload rewrite.
2. **`instructions` must be non-empty** — langchain never emits it for the
   Responses API.
3. **No `system`/`developer` messages in `input`** — HTTP 400 *"System messages
   are not allowed"*. langchain puts the system prompt in `input`; we **hoist**
   it into `instructions`.
4. **`max_output_tokens` is stripped.**

All four are applied in `CodexChatOpenAI._get_request_payload` (the single method
langchain calls before serialization on both the sync and async paths) — not in
an httpx event-hook, which would not modify the actually-sent `request.stream`
and would crash the async path.

5. **`response.completed` carries no `output`** — unlike api.openai.com, the
   Codex backend streams text via `response.output_text.delta` and omits the
   final `output` array. langchain's reconstruction does
   `for output in response.output` → `TypeError`. A small, idempotent shim
   (installed only on the OAuth path) coerces a missing `output` to `[]`; the
   text has already been delivered by the deltas. It is a strict no-op for
   standard OpenAI responses.

## Testing
Unit tests live in `tests/test_oauth_*.py` (PKCE, store/refresh, auth retry,
payload rewrite, shim, wiring, client headers, CLI, login security paths) and run
fully offline. `scripts/oauth_smoke.py` is a manual one-call live check that
requires a real login.
