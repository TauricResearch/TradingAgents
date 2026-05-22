# Intentionally minimal — no secrets, no config, no credentials.
# The image is public and safe to push to any registry.
#
# Everything runtime-specific (LLM provider, API keys, skill config)
# lives in the Fly.io persistent volume at /opt/data and is injected
# via `fly secrets set` or configured via `fly ssh console` after deploy.
#
# Deploy order:
#   1. fly deploy          — boots gateway, mounts volume
#   2. fly ssh console     — configure LLM, install seed skills, run migrations
#   3. fly secrets set     — inject credentials, restart

FROM nousresearch/hermes-agent:main

# Hermes tool wrappers: tradingagents, ib_executor, telegram
COPY hermes_tools/ /opt/hermes_tools/

# System prompt loaded by Hermes at startup
COPY hermes_config/system_prompt.md /opt/hermes_config/system_prompt.md

# Seed skills installed once via SSH: trade-setup, risk-rules, position-sizing
COPY hermes_config/seed_skills/ /opt/seed_skills/

# One-time setup scripts run via SSH after first deploy
COPY scripts/ /opt/scripts/
