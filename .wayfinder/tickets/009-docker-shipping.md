---
id: 009
title: "Decide: how the web UI ships in Docker"
labels: [wayfinder:grilling]
status: closed
assignee: JMAN730
blocked-by: []
---

## Question

Dockerfile currently ends `ENTRYPOINT ["tradingagents"]` (bare CLI) and docker-compose runs the CLI interactively. How does `tradingagents web` fit?

- Does the image install the `[web]` extra by default, or a separate build stage/tag?
- Compose service for the web server: port mapping (8035), bind address inside the container must be 0.0.0.0 (127.0.0.1 binding is unreachable through Docker port publishing) — how does that interact with the 002 Host-allowlist decision (published port on the host is still localhost-only via `127.0.0.1:8035:8035` mapping; allowlist must accept the mapped Host header)?
- Env passthrough for API keys and `TRADINGAGENTS_*` vars; volume for `~/.tradingagents` (results, memory, cache) so history survives container restarts.
- Keep the 002 `@app.callback` compat so the existing CLI entrypoint behavior is unchanged.

## Resolution

Decided from Dockerfile/docker-compose facts (multi-stage venv build, non-root `appuser`, `ENTRYPOINT ["tradingagents"]`, shared `tradingagents_data` volume at `/home/appuser/.tradingagents`, ollama profile).

1. **One image, `[web]` extra installed by default:** builder stage becomes `pip install --no-cache-dir ".[web]"`. Three extra wheels are negligible against the image size; no tag/stage matrix. CLI-only usage is unaffected thanks to 002's lazy imports.
2. **New compose service `tradingagents-web`:** ENTRYPOINT unchanged, `command: ["web", "--host", "0.0.0.0", "--port", "8035"]`, same `env_file: .env`, same `tradingagents_data` volume — so container CLI runs and web runs share one history (006). No `tty`/`stdin_open`. Optional compose healthcheck against a new lightweight `GET /api/health` endpoint (added to the spec's API surface; also useful in tests).
3. **`--host` flag added** to the `web` subcommand (default `127.0.0.1`). Inside the container it must be `0.0.0.0` — Docker port publishing cannot reach a loopback-bound server.

Security posture (written plainly):
- The compose port mapping is `127.0.0.1:8035:8035` — published on the host's loopback only. Binding 0.0.0.0 inside the container is safe precisely because the host-side publish is loopback-only; the docs must warn against changing the mapping to `0.0.0.0:8035:8035` or `8035:8035`, which would expose the unauthenticated server to the network.
- Host-allowlist interaction: Docker's port proxy forwards the browser's `Host` header verbatim, so `Host: 127.0.0.1:8035` still matches the {localhost, 127.0.0.1, [::1]} allowlist inside the container. The allowlist must compare the hostname component only (port-agnostic) so remapped host ports (e.g. `127.0.0.1:9000:8035`) keep working; verify at implementation that Starlette's TrustedHostMiddleware strips the port before matching (believed yes), otherwise strip it explicitly.
4. **No ollama web service variant.** Users combining web + ollama set `TRADINGAGENTS_LLM_PROVIDER=ollama` in `.env`; keeps the compose matrix flat.
5. **Existing services untouched:** 002's `@app.callback(invoke_without_command=True)` keeps bare `tradingagents` (ENTRYPOINT, interactive CLI service) behaving exactly as today.
