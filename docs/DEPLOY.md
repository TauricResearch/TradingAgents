# Deploy TradingAgents on shimazu

**Live URL:** https://tradingagents.quiltyapp.com  
**Alias:** https://TradingAgents.quiltyapp.com (same vhost `server_name`)

## Stack

| Piece | Detail |
|-------|--------|
| App | `scripts/site_server.py` (Python, port **8794**) |
| systemd | `~/.config/systemd/user/tradingagents-site.service` |
| nginx + TLS | `scripts/install_site.sh` → certbot |
| Auth | Webbit Spina SSO (same secret as agents.quiltyapp.com) |
| Broker books | agentRobin bridge (`--account` / `/api/portfolio`) |

## Install / refresh

```bash
cd /home/marckoby/dev/TradingAgents
# venv once
python3 -m venv .venv && .venv/bin/pip install -e .
./scripts/install_site.sh
curl -sI https://tradingagents.quiltyapp.com/healthz
```

## Upstream sync

```bash
./scripts/sync_upstream.sh
```

## Env

- `.env` — LLM API keys (mode 0600, gitignored)
- `AGENTROBIN_ROOT` — bridge to FakeBroker / Schwab / RH
- `TRADINGAGENTS_SITE_AUTH=sso` (or `disabled` for local-only)
