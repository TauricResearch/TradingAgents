#!/usr/bin/env bash
# Cloudflare Tunnel launcher (optional — only if you want public ingress
# without opening a router port). Configure your tunnel via
#   cloudflared tunnel login
#   cloudflared tunnel create <NAME>
#   cloudflared tunnel route dns <NAME> <hostname>
# then point this script at the tunnel name via TRADINGAGENTS_TUNNEL_NAME and
# its config file via TRADINGAGENTS_TUNNEL_CONFIG.
set -euo pipefail

TUNNEL_NAME="${TRADINGAGENTS_TUNNEL_NAME:-tradingagents}"
TUNNEL_CONFIG="${TRADINGAGENTS_TUNNEL_CONFIG:-$HOME/.cloudflared/${TUNNEL_NAME}.yml}"

exec cloudflared tunnel --config "$TUNNEL_CONFIG" run "$TUNNEL_NAME"
