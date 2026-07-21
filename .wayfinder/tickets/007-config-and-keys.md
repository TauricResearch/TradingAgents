---
id: 007
title: "Decide: config and API-key handling in the web UI"
labels: [wayfinder:grilling]
status: closed
assignee: JMAN730
blocked-by: []
---

## Question

How much of `DEFAULT_CONFIG` / `.env` does the UI expose?

- API keys: read-only presence indicator (set/unset per provider) vs editable in UI. (Recommended: presence indicator only — never render or accept key values in the browser; keys stay in `.env`/env vars.)
- Run-level config (provider, models, debate rounds, online tools): form fields per run vs global settings page vs both.
- Where web-chosen settings persist between sessions, if at all.

## Resolution

Decided from verified config-surface facts (api_key_env.py: 19 providers with canonical key-env mapping; default_config.py: `TRADINGAGENTS_*` env-override table; CLI `ensure_api_key` interactive prompt is terminal-only).

**API keys — presence only, never values (security-critical):**
- `GET /api/providers` returns per provider: name, model catalog, key env-var name, and key status as a plain boolean (`present` / `missing` / `not-required` for bedrock/ollama, `optional` for openai_compatible). Never the key value and never a masked prefix — prefixes leak entropy and invite "show a bit more" drift.
- No endpoint accepts a key as input. Keys are configured in `.env`/environment as today; the UI shows the env-var name with a "add to .env and restart the server" hint. Rationale: browser-origin secret entry would put keys on a localhost HTTP surface whose only guard is the Host allowlist; a `.env`-editing developer audience makes that risk pure downside.
- Pre-run validation: `POST /api/runs` checks key presence for the selected provider before spawning the run task and fails with a clear error naming the env var (replaces the CLI's interactive prompt).
- `backend_url` is treated as secret-adjacent: users of keyed OpenAI-compatible relays sometimes embed tokens in the URL. The API never echoes the server-side `backend_url` value back to the browser; the configure form's backend-url field (shown for openai_compatible) is write-only.

**Run-level config — per-run form fields, mirroring the CLI selections:** ticker, date, asset type, analysts, research depth (mapped to `max_debate_rounds`/`max_risk_discuss_rounds` presets as the CLI does), provider + deep/quick models (from the model catalog), thinking/effort knobs (`google_thinking_level`, `openai_reasoning_effort`, `anthropic_effort`) in a collapsed "advanced" group. Server builds `config = DEFAULT_CONFIG.copy()` + request overrides — same shape the CLI uses; `TRADINGAGENTS_*` env vars keep supplying the base defaults.

**Persistence:** last-used run settings saved server-side to `~/.tradingagents/web_settings.json` and loaded as the configure form's defaults (excluding anything secret-adjacent: no backend_url). No global settings page in v1; the sidebar Settings entry is a read-only panel: provider key presence, results/memory/cache paths, effective non-secret defaults.

**Config exposure:** `GET /api/config` returns an explicit whitelist of non-secret keys (results_dir, llm defaults, debate rounds, output_language, checkpoint_enabled, news limits). Never a raw `DEFAULT_CONFIG` dump — future config keys must opt in, so a later secret-bearing key can't leak by default.
