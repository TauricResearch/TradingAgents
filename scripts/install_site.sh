#!/usr/bin/env bash
# Publish TradingAgents at https://tradingagents.quiltyapp.com (and TradingAgents.quiltyapp.com).
# Pattern mirrors agentRobin scripts/install_agents_site.sh (DNS via Governor, nginx, certbot).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE="${TRADINGAGENTS_SITE_HOST:-tradingagents.quiltyapp.com}"
SITE_ALIAS="${TRADINGAGENTS_SITE_ALIAS:-TradingAgents.quiltyapp.com}"
PORT="${TRADINGAGENTS_SITE_PORT:-8794}"
SERVER_SLUG="${TRADINGAGENTS_SITE_SERVER_SLUG:-shimazu}"
GOVERNOR_SSH="${GOVERNOR_SSH:-quilty_ops@ninja.quilty.app}"
GOVERNOR_APP="${GOVERNOR_APP:-/home/quilty_ops/governor.quilty.app}"
STATUS_FILE="$ROOT/state/site_install.json"
mkdir -p "$(dirname "$STATUS_FILE")" "$ROOT/logs"

dns_status="unknown"; nginx_status="unknown"; tls_status="unknown"; notes=()

resolves() { getent hosts "$SITE" >/dev/null 2>&1 || host "$SITE" >/dev/null 2>&1; }

# ---------------------------------------------------------------- 1. DNS
if resolves; then
  dns_status="ok"
else
  echo "tradingagents site: $SITE does not resolve — requesting CNAME from Site Governor"
  gov_cmd="cd '$GOVERNOR_APP' && set -a && { [ -r /etc/quilty/governor.env ] && . /etc/quilty/governor.env; true; } && set +a && \
env RAILS_ENV=production HOSTNAME='$SITE' SERVER_SLUG='$SERVER_SLUG' bin/rails dns:provision_developer_cname"
  id_opts=()
  for key in ${GOVERNOR_SSH_IDENTITY:-} "$HOME"/.ssh/id_ed25519* "$HOME"/.ssh/id_ecdsa* "$HOME"/.ssh/id_rsa*; do
    [ -f "$key" ] && [ "${key%.pub}" = "$key" ] && [ "${#id_opts[@]}" -lt 10 ] && id_opts+=(-i "$key")
  done
  out=""
  for target in "$GOVERNOR_SSH" quilty_ops@ninja quilty_ops@74.208.14.103; do
    if out="$(ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new ${id_opts[@]+"${id_opts[@]}"} "$target" "$gov_cmd" 2>&1)"; then
      dns_status="requested"; notes+=("governor: ${out//\"/\'}"); break
    fi
    echo "tradingagents site: governor via $target failed"
  done
  [ "$dns_status" = "requested" ] || { dns_status="failed"; notes+=("governor CNAME request failed"); }
fi

# ---------------------------------------------------------------- 2. nginx
VHOST="/etc/nginx/sites-available/$SITE"
read -r -d '' CONF <<NGINX || true
# Managed by TradingAgents scripts/install_site.sh
server {
  listen 80;
  listen [::]:80;
  server_name $SITE $SITE_ALIAS;

  location / {
    proxy_pass http://127.0.0.1:$PORT;
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_read_timeout 120s;
  }
}
NGINX

if command -v nginx >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
  if [ -f "$VHOST" ] && grep -q "ssl_certificate" "$VHOST"; then
    nginx_status="ok (certbot-managed, left as is)"
  else
    printf '%s\n' "$CONF" | sudo -n tee "$VHOST" >/dev/null
    sudo -n ln -sf "$VHOST" "/etc/nginx/sites-enabled/$SITE"
    if sudo -n nginx -t >/dev/null 2>&1; then
      sudo -n systemctl reload nginx && nginx_status="ok"
    else
      nginx_status="config_test_failed"
      sudo -n rm -f "/etc/nginx/sites-enabled/$SITE"
      notes+=("nginx -t failed; vhost disabled")
    fi
  fi
else
  nginx_status="skipped (no nginx or no passwordless sudo)"
fi

# ---------------------------------------------------------------- 3. TLS
if [ -f "$VHOST" ] && grep -q "ssl_certificate" "$VHOST"; then
  tls_status="ok"
elif resolves && command -v certbot >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
  if sudo -n certbot --nginx -d "$SITE" -d "$SITE_ALIAS" --non-interactive --agree-tos --redirect --keep-until-expiring >/dev/null 2>&1 \
     || sudo -n certbot --nginx -d "$SITE" --non-interactive --agree-tos --redirect --keep-until-expiring >/dev/null 2>&1; then
    tls_status="ok"
  else
    tls_status="certbot_failed"
    notes+=("certbot failed — DNS may still be propagating")
  fi
else
  tls_status="pending_dns"
fi

# ---------------------------------------------------------------- 4. systemd user unit
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
UNIT="$UNIT_DIR/tradingagents-site.service"
PYTHON_BIN="${TRADINGAGENTS_PYTHON:-$ROOT/.venv/bin/python3}"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="$(command -v python3)"
cat > "$UNIT" <<EOF
[Unit]
Description=TradingAgents site (tradingagents.quiltyapp.com)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
Environment=TRADINGAGENTS_ROOT=$ROOT
Environment=AGENTROBIN_ROOT=${AGENTROBIN_ROOT:-/home/marckoby/dev/agentRobin}
Environment=TRADINGAGENTS_SITE_PORT=$PORT
Environment=TRADINGAGENTS_PUBLIC_URL=https://$SITE
Environment=TRADINGAGENTS_SITE_AUTH=sso
Environment=PYTHONUNBUFFERED=1
# Load LLM keys without printing them
EnvironmentFile=-$ROOT/.env
ExecStart=$PYTHON_BIN $ROOT/scripts/site_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
systemctl --user daemon-reload
systemctl --user enable --now tradingagents-site.service
svc_status="$(systemctl --user is-active tradingagents-site.service 2>/dev/null || echo failed)"

health="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$PORT/healthz" 2>/dev/null || echo 000)"

python3 - "$STATUS_FILE" "$SITE" "$dns_status" "$nginx_status" "$tls_status" "$health" "$svc_status" "${notes[@]+"${notes[@]}"}" <<'PY'
import json, sys, datetime
path, site, dns, ngx, tls, health, svc, *notes = sys.argv[1:]
json.dump({
  "site": site,
  "alias": "TradingAgents.quiltyapp.com",
  "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "dns": dns, "nginx": ngx, "tls": tls,
  "healthz": health, "service": svc, "notes": notes
}, open(path, "w"), indent=2)
print(json.dumps({"dns": dns, "nginx": ngx, "tls": tls, "healthz": health, "service": svc}, indent=2))
PY

# etckeeper if /etc changed
if [ -d /etc/.git ] && command -v sudo >/dev/null && sudo -n true 2>/dev/null; then
  if sudo -n /home/quilty_ops/governor.quilty.app/scripts/host/etckeeper-commit.sh \
      "TradingAgents: nginx vhost $SITE" 2>/dev/null; then
    notes+=("etckeeper committed")
  fi
fi

echo "tradingagents site: dns=$dns_status nginx=$nginx_status tls=$tls_status healthz=$health service=$svc_status"
exit 0
