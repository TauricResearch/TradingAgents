#!/usr/bin/env bash
#
# In-place updater — TEK BAŞINA çalıştırılmaz. install.sh bunu
# /usr/local/sbin/tradingagents-update olarak (root sahipli) kopyalar ve
# bir oneshot systemd unit'iyle tetikler. Backend yalnızca o unit'i
# `sudo -n systemctl start --no-block` ile başlatır.
#
# Akış: git pull + bağımlılıklar + frontend build (RUN_USER olarak) →
# ana servisi yeniden başlat (root). Çekilen kod RUN_USER olarak build
# edildiği için ayrıcalık yükseltmesi yoktur; yalnızca restart root'tur.
#
set -uo pipefail

CONF="${TRADINGAGENTS_UPDATE_CONF:-/etc/tradingagents/update.env}"
# shellcheck disable=SC1090
[ -f "$CONF" ] && . "$CONF"
: "${PROJECT_ROOT:?update.env eksik: PROJECT_ROOT}"
: "${SERVICE_NAME:?update.env eksik: SERVICE_NAME}"
: "${RUN_USER:?update.env eksik: RUN_USER}"
: "${VENV:?update.env eksik: VENV}"

STATUS="$PROJECT_ROOT/.update.json"
LOG="$PROJECT_ROOT/.update.log"

# RUN_USER'ın HOME'u — npm/pip/git cache'leri buraya yazsın (yoksa /root'a
# yazmaya çalışıp izin hatası verir).
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
[ -n "$RUN_HOME" ] || RUN_HOME="/home/$RUN_USER"

now()  { date -u +%Y-%m-%dT%H:%M:%SZ; }
asuser() { runuser -u "$RUN_USER" -- env "HOME=$RUN_HOME" "$@"; }

write_status() { # state [error-message]
    local err="null"
    [ -n "${2:-}" ] && err="$(printf '%s' "$2" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '"hata"')"
    printf '{"state":"%s","at":"%s","from":"%s","to":"%s","error":%s}\n' \
        "$1" "$(now)" "${FROM:-?}" "${TO:-?}" "$err" > "$STATUS" 2>/dev/null || true
    chown "$RUN_USER":"$RUN_USER" "$STATUS" 2>/dev/null || true
}
log() { echo "[$(now)] $*" >> "$LOG" 2>/dev/null || true; chown "$RUN_USER":"$RUN_USER" "$LOG" 2>/dev/null || true; }

FROM="$(asuser git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo '?')"
TO="$FROM"
write_status running
log "=== Güncelleme başladı ($FROM) ==="

fail() { log "HATA: $1"; TO="$(asuser git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo '?')"; write_status failed "$1"; exit 1; }
run()  { log "+ $*"; if ! asuser "$@" >>"$LOG" 2>&1; then fail "Komut başarısız: $*"; fi; }

# 1. Kodu çek (sadece fast-forward — yerel commit'ler varsa durur)
run git -C "$PROJECT_ROOT" fetch --all --quiet
asuser git -C "$PROJECT_ROOT" pull --ff-only >>"$LOG" 2>&1 || fail "git pull --ff-only başarısız (yerel değişiklik/diverge olabilir)"

# 2. Backend bağımlılıkları (requirements değiştiyse)
run "$VENV/bin/pip" install -q -r "$PROJECT_ROOT/backend/requirements.txt"

# 3. Frontend build (değiştiyse)
if [ -d "$PROJECT_ROOT/frontend" ]; then
    run bash -c "cd '$PROJECT_ROOT/frontend' && { npm ci || npm install; } && npm run build"
fi

TO="$(asuser git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo '?')"
log "Build tamam: $FROM -> $TO. Servis yeniden başlatılıyor."
write_status done

# 4. Ana servisi yeniden başlat (root — bu updater ayrı bir cgroup'ta olduğu
#    için restart bu süreci öldürmez)
systemctl restart "$SERVICE_NAME"
log "=== Güncelleme tamamlandı ($TO) ==="
