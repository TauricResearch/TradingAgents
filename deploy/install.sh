#!/usr/bin/env bash
#
# TradingAgents — tek komutla Linux kurulum + systemd servisi.
#
#   sudo bash deploy/install.sh
#
# Yaptıkları (hepsi idempotent — tekrar çalıştırılabilir):
#   1. Sistem bağımlılıkları: Python 3.10+, Node 20, PostgreSQL, git, curl
#   2. Python sanal ortamı + backend/requirements.txt
#   3. Frontend build (npm) -> frontend/dist (backend tarafından sunulur)
#   4. PostgreSQL veritabanı + kullanıcı
#   5. .env üretimi (güvenli rastgele SECRET_KEY / ENCRYPTION_KEY / DB şifresi /
#      admin şifresi) — yalnızca .env yoksa
#   6. systemd servisi (tek process: in-memory WebSocket + APScheduler cron
#      birden çok worker ile bozulur, bu yüzden uvicorn tek process çalışır)
#   7. Servisi enable + start eder, sağlık kontrolü yapar
#
# Ortam değişkenleriyle özelleştirme (opsiyonel):
#   SERVICE_NAME=tradingagents  SERVICE_USER=<kullanıcı>  APP_PORT=8000
#   ADMIN_USERNAME=admin        ADMIN_PASSWORD=<düz şifre>  NODE_MAJOR=20
#   SKIP_DB=1 (harici PostgreSQL kullan)   BUILD_FRONTEND=0 (UI build'i atla)
#
set -euo pipefail

# ── Ayarlar (ortam değişkeniyle override edilebilir) ────────────────────────────
SERVICE_NAME="${SERVICE_NAME:-tradingagents}"
APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8000}"
DB_NAME_DEFAULT="${DB_NAME:-tradingagents}"
DB_USER_DEFAULT="${DB_USER:-tradingagents}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
NODE_MAJOR="${NODE_MAJOR:-20}"
SKIP_DB="${SKIP_DB:-0}"
BUILD_FRONTEND="${BUILD_FRONTEND:-1}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$PROJECT_ROOT/.venv"
ENV_FILE="$PROJECT_ROOT/.env"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Servisi çalıştıracak kullanıcı: belirtilmemişse sudo'yu çağıran kişi.
RUN_USER="${SERVICE_USER:-${SUDO_USER:-root}}"

# ── Loglama ─────────────────────────────────────────────────────────────────────
info() { printf '\033[1;34m[*]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

# ── Ön kontroller ───────────────────────────────────────────────────────────────
[ "$(id -u)" -eq 0 ] || die "Bu script root gerektirir:  sudo bash deploy/install.sh"
[ -f "$PROJECT_ROOT/backend/requirements.txt" ] || die "backend/requirements.txt bulunamadı — proje kökünden çalıştırın."
[ -d "$PROJECT_ROOT/frontend" ] || die "frontend/ bulunamadı — proje yapısı beklenenden farklı."
command -v systemctl >/dev/null || die "systemd (systemctl) bulunamadı — bu script systemd tabanlı dağıtımlar içindir."

id "$RUN_USER" &>/dev/null || {
    info "Servis kullanıcısı '$RUN_USER' oluşturuluyor..."
    useradd --system --create-home --shell /usr/sbin/nologin "$RUN_USER"
}

# ── Paket yöneticisi tespiti ────────────────────────────────────────────────────
if   command -v apt-get >/dev/null; then PM=apt
elif command -v dnf     >/dev/null; then PM=dnf
elif command -v yum     >/dev/null; then PM=yum
else die "Desteklenen paket yöneticisi yok (apt/dnf/yum)."; fi
info "Paket yöneticisi: $PM"

pm_install() {
    case "$PM" in
        apt) DEBIAN_FRONTEND=noninteractive apt-get install -y "$@" ;;
        dnf) dnf install -y "$@" ;;
        yum) yum install -y "$@" ;;
    esac
}

# ── 1. Sistem bağımlılıkları ────────────────────────────────────────────────────
info "Sistem paketleri kuruluyor..."
if [ "$PM" = apt ]; then
    apt-get update -y
    pm_install python3 python3-venv python3-dev build-essential libpq-dev git curl ca-certificates
    [ "$SKIP_DB" = 1 ] || pm_install postgresql postgresql-contrib
else
    pm_install python3 python3-devel gcc gcc-c++ make git curl
    [ "$SKIP_DB" = 1 ] || pm_install postgresql-server postgresql-contrib || true
fi
ok "Sistem paketleri hazır."

# ── Python 3.10+ seç ────────────────────────────────────────────────────────────
pick_python() {
    local c v
    for c in python3.13 python3.12 python3.11 python3.10 python3; do
        command -v "$c" >/dev/null || continue
        v=$("$c" -c 'import sys;print(sys.version_info[0]*100+sys.version_info[1])' 2>/dev/null || echo 0)
        if [ "$v" -ge 310 ]; then echo "$c"; return 0; fi
    done
    return 1
}
PYTHON="$(pick_python)" || die "Python 3.10+ bulunamadı. Lütfen python3.10+ kurun."
info "Python: $PYTHON ($("$PYTHON" --version 2>&1))"

# ── 2. Node 20 (Vite 8 için gerekli) ───────────────────────────────────────────
if [ "$BUILD_FRONTEND" = 1 ]; then
    node_major() { command -v node >/dev/null && node -v | sed 's/v\([0-9]*\).*/\1/' || echo 0; }
    if [ "$(node_major)" -lt "$NODE_MAJOR" ]; then
        info "Node $NODE_MAJOR kuruluyor (NodeSource)..."
        if [ "$PM" = apt ]; then
            curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" -o /tmp/nodesource.sh
            bash /tmp/nodesource.sh >/dev/null
            pm_install nodejs
        else
            curl -fsSL "https://rpm.nodesource.com/setup_${NODE_MAJOR}.x" -o /tmp/nodesource.sh
            bash /tmp/nodesource.sh >/dev/null
            pm_install nodejs
        fi
    fi
    ok "Node $(node -v) / npm $(npm -v)"
fi

# ── 3. Python venv + bağımlılıklar ──────────────────────────────────────────────
info "Python sanal ortamı hazırlanıyor: $VENV"
[ -d "$VENV" ] || "$PYTHON" -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip wheel >/dev/null
info "backend/requirements.txt kuruluyor (birkaç dakika sürebilir)..."
"$VENV/bin/pip" install -r "$PROJECT_ROOT/backend/requirements.txt"
ok "Python bağımlılıkları kuruldu."

# ── 4. Frontend build ───────────────────────────────────────────────────────────
if [ "$BUILD_FRONTEND" = 1 ]; then
    info "Frontend derleniyor (npm)..."
    pushd "$PROJECT_ROOT/frontend" >/dev/null
    if [ -f package-lock.json ]; then npm ci || npm install; else npm install; fi
    npm run build
    popd >/dev/null
    [ -f "$PROJECT_ROOT/frontend/dist/index.html" ] || die "Frontend build başarısız (dist/index.html yok)."
    ok "Frontend derlendi -> frontend/dist"
else
    warn "BUILD_FRONTEND=0 — UI derlenmedi (yalnızca API)."
fi

# ── 5. .env (yalnızca yoksa üret) ───────────────────────────────────────────────
GENERATED_ADMIN_PW=""
if [ ! -f "$ENV_FILE" ]; then
    info ".env üretiliyor (güvenli rastgele secret'lar)..."
    SECRET_KEY=$("$PYTHON" -c 'import secrets;print(secrets.token_hex(32))')
    # Fernet anahtarı = 32 baytın urlsafe base64'ü (stdlib ile üretilebilir)
    ENCRYPTION_KEY=$("$PYTHON" -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')
    DB_USER="$DB_USER_DEFAULT"
    DB_NAME="$DB_NAME_DEFAULT"
    DB_PASS=$("$PYTHON" -c 'import secrets;print(secrets.token_urlsafe(24))')  # @ : / içermez
    ADMIN_PASSWORD="${ADMIN_PASSWORD:-$("$PYTHON" -c 'import secrets;print(secrets.token_urlsafe(12))')}"
    GENERATED_ADMIN_PW="$ADMIN_PASSWORD"
    ADMIN_HASH=$("$VENV/bin/python" -c 'import bcrypt,sys;print(bcrypt.hashpw(sys.argv[1].encode(),bcrypt.gensalt()).decode())' "$ADMIN_PASSWORD")

    # Değerler tek tırnak içinde yazılır: bcrypt hash "$" içerir ve dotenv/systemd
    # bunu değişken olarak genişletmemeli. CORS_ORIGINS de JSON köşeli parantez içerir.
    {
        printf "SECRET_KEY='%s'\n"          "$SECRET_KEY"
        printf "ENCRYPTION_KEY='%s'\n"      "$ENCRYPTION_KEY"
        printf "ADMIN_USERNAME='%s'\n"      "$ADMIN_USERNAME"
        printf "ADMIN_PASSWORD_HASH='%s'\n" "$ADMIN_HASH"
        printf "DATABASE_URL='postgresql+asyncpg://%s:%s@localhost:5432/%s'\n" "$DB_USER" "$DB_PASS" "$DB_NAME"
        printf "CORS_ORIGINS='[\"http://localhost:%s\"]'\n" "$APP_PORT"
        printf '\n# LLM sağlayıcı anahtarları — en az birini doldurun, sonra: systemctl restart %s\n' "$SERVICE_NAME"
        printf 'OPENAI_API_KEY=\nANTHROPIC_API_KEY=\nGOOGLE_API_KEY=\nXAI_API_KEY=\nDEEPSEEK_API_KEY=\n'
        printf '\n# Veri sağlayıcı anahtarları (opsiyonel)\nALPHA_VANTAGE_API_KEY=\nREDDIT_CLIENT_ID=\nREDDIT_CLIENT_SECRET=\n'
    } > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    ok ".env oluşturuldu."
else
    info ".env zaten var — korunuyor (secret'lar yeniden üretilmedi)."
fi

# Postgres kurulumu için DB bilgilerini .env'den oku (kaynak tek: .env)
read DB_USER DB_PASS DB_NAME < <(
    "$VENV/bin/python" - "$ENV_FILE" <<'PY'
import sys, urllib.parse as u
from dotenv import dotenv_values
url = dotenv_values(sys.argv[1]).get("DATABASE_URL", "")
p = u.urlsplit(url)
print(p.username or "", p.password or "", (p.path or "/").lstrip("/"))
PY
) || true
[ -n "${DB_NAME:-}" ] || die "DATABASE_URL .env içinden ayrıştırılamadı."

# ── 6. PostgreSQL veritabanı + kullanıcı ────────────────────────────────────────
if [ "$SKIP_DB" = 1 ]; then
    warn "SKIP_DB=1 — PostgreSQL kurulumu atlandı (harici DB bekleniyor)."
else
    info "PostgreSQL yapılandırılıyor..."
    if [ "$PM" != apt ]; then
        # RHEL ailesi: initdb gerekli, ve 127.0.0.1 için parola auth'a geç (en iyi çaba)
        if [ ! -s /var/lib/pgsql/data/PG_VERSION ]; then
            (postgresql-setup --initdb || /usr/bin/postgresql-setup initdb) || true
        fi
        HBA=/var/lib/pgsql/data/pg_hba.conf
        [ -f "$HBA" ] && sed -i 's/^\(host\s\+all\s\+all\s\+127.0.0.1\/32\s\+\)ident/\1scram-sha-256/' "$HBA" || true
    fi
    systemctl enable --now postgresql >/dev/null 2>&1 || systemctl enable --now postgresql || die "postgresql başlatılamadı."

    # Soketin hazır olmasını bekle (root olduğumuz için runuser yeterli; sudo gerekmez)
    for _ in $(seq 1 10); do runuser -u postgres -- psql -tAc 'SELECT 1' >/dev/null 2>&1 && break; sleep 1; done

    psql_admin() { runuser -u postgres -- psql -v ON_ERROR_STOP=1 "$@"; }
    if psql_admin -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
        psql_admin -c "ALTER ROLE \"$DB_USER\" LOGIN PASSWORD '$DB_PASS';"
    else
        psql_admin -c "CREATE ROLE \"$DB_USER\" LOGIN PASSWORD '$DB_PASS';"
    fi
    if ! psql_admin -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
        runuser -u postgres -- createdb -O "$DB_USER" "$DB_NAME"
    fi
    ok "PostgreSQL hazır (db=$DB_NAME, user=$DB_USER)."
fi

# ── Dosya sahipliği ─────────────────────────────────────────────────────────────
info "Dosya sahipliği '$RUN_USER' kullanıcısına veriliyor..."
chown -R "$RUN_USER":"$RUN_USER" "$VENV" 2>/dev/null || true
chown "$RUN_USER":"$RUN_USER" "$ENV_FILE" 2>/dev/null || true
[ -d "$PROJECT_ROOT/frontend/dist" ] && chown -R "$RUN_USER":"$RUN_USER" "$PROJECT_ROOT/frontend/dist" 2>/dev/null || true

# ── 7. systemd servisi ──────────────────────────────────────────────────────────
info "systemd servisi yazılıyor: $UNIT_FILE"
cat > "$UNIT_FILE" <<EOF
[Unit]
Description=TradingAgents Web (FastAPI + multi-agent LLM trading)
After=network-online.target postgresql.service
Wants=network-online.target postgresql.service

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$PROJECT_ROOT
Environment=PYTHONPATH=$PROJECT_ROOT
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=$ENV_FILE
# TEK PROCESS ZORUNLU: in-memory WebSocket yöneticisi + APScheduler cron birden
# çok worker ile çoğaltılır (çift analiz / bozuk WS). --workers EKLEMEYİN.
ExecStart=$VENV/bin/uvicorn backend.main:app --host $APP_HOST --port $APP_PORT
Restart=on-failure
RestartSec=5
# Düşük portlara (örn. 80) bağlanabilmek için
AmbientCapabilities=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1 || true
systemctl restart "$SERVICE_NAME"
ok "Servis başlatıldı: $SERVICE_NAME"

# Güvenlik duvarı (opsiyonel, ufw aktifse)
if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
    ufw allow "${APP_PORT}/tcp" >/dev/null 2>&1 || true
    info "ufw: ${APP_PORT}/tcp portu açıldı."
fi

# ── Sağlık kontrolü ─────────────────────────────────────────────────────────────
info "Sağlık kontrolü yapılıyor..."
HEALTHY=0
for _ in $(seq 1 15); do
    if curl -fsS "http://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1; then HEALTHY=1; break; fi
    sleep 1
done

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
if [ "$HEALTHY" = 1 ]; then
    ok "============================================================"
    ok " TradingAgents çalışıyor 🎉"
    ok "============================================================"
    echo "  Arayüz   :  http://localhost:${APP_PORT}"
    [ -n "$LAN_IP" ] && echo "             http://${LAN_IP}:${APP_PORT}"
    echo "  Admin    :  ${ADMIN_USERNAME}"
    if [ -n "$GENERATED_ADMIN_PW" ]; then
        echo "  Şifre    :  ${GENERATED_ADMIN_PW}"
        warn "Bu şifreyi kaydedin — bir daha gösterilmeyecek."
    else
        echo "  Şifre    :  (mevcut .env'deki ADMIN_PASSWORD_HASH kullanılıyor)"
    fi
    echo
    echo "  ⚠  LLM anahtarı ekleyin:  nano $ENV_FILE   sonra: systemctl restart $SERVICE_NAME"
    echo
    echo "  Yönetim:"
    echo "    journalctl -u $SERVICE_NAME -f      # canlı log"
    echo "    systemctl restart|stop $SERVICE_NAME"
    echo "    bash deploy/uninstall.sh            # kaldır"
else
    err "Servis sağlık kontrolünden geçemedi. Logları inceleyin:"
    err "    journalctl -u $SERVICE_NAME -n 50 --no-pager"
    exit 1
fi
