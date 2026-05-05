#!/usr/bin/env bash
# First-time deploy of the TradingAgents GUI to the Synology NAS.
#
# What this does on the NAS:
#   1. mkdir -p $NAS_REPO_PATH and clone the fork into it
#   2. mkdir -p $NAS_DATA_PATH and chown to UID:GID 1000:1000
#      (matches the appuser inside the container)
#   3. ensure .env exists (warn + abort if missing — keys must be filled in)
#   4. docker compose build gui
#   5. docker compose up -d gui
#   6. wait for healthcheck and tail the first chunk of logs
#
# Idempotent: safe to run multiple times. If the repo is already cloned
# it pulls instead of cloning. .env is never overwritten.
#
# Usage (from the local machine, after credentials.local is filled in):
#     scripts/nas/deploy.sh
#
# To pass a different fork URL the very first time:
#     FORK_URL=https://github.com/youruser/TradingAgents.git scripts/nas/deploy.sh

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRED_FILE="$DIR/credentials.local"
NAS_CMD="$DIR/nas-cmd.sh"

[[ -f "$CRED_FILE" ]] || { echo "Missing $CRED_FILE — see credentials.local.example"; exit 2; }
# shellcheck disable=SC1090
source "$CRED_FILE"

: "${NAS_HOST:?}"; : "${NAS_USER:?}"
NAS_REPO_PATH="${NAS_REPO_PATH:-/volume1/docker/tradingagents}"
NAS_DATA_PATH="${NAS_DATA_PATH:-/volume1/docker/tradingagents/data}"
NAS_GIT_BRANCH="${NAS_GIT_BRANCH:-main}"
FORK_URL="${FORK_URL:-https://github.com/mrh335/TradingAgents.git}"

echo "[deploy] target NAS: $NAS_USER@$NAS_HOST"
echo "[deploy] repo path:  $NAS_REPO_PATH"
echo "[deploy] data path:  $NAS_DATA_PATH"
echo "[deploy] fork:       $FORK_URL @ $NAS_GIT_BRANCH"
echo

# Step 1 — clone or pull, set up data dir, check for .env
echo "[deploy] ----- step 1: clone + set up paths -----"
"$NAS_CMD" "set -e
mkdir -p '$NAS_REPO_PATH' '$NAS_DATA_PATH'

if [ -d '$NAS_REPO_PATH/.git' ]; then
    # Already a git clone — pull.
    cd '$NAS_REPO_PATH'
    git fetch --all --prune
    git checkout '$NAS_GIT_BRANCH'
    git pull --ff-only
elif [ -d '$NAS_REPO_PATH' ]; then
    # Directory exists (probably containing only data/) but no .git yet.
    # Use init+fetch+checkout instead of clone — clone refuses non-empty
    # targets, but this pattern coexists with the persistent data/ dir.
    cd '$NAS_REPO_PATH'
    if [ ! -d .git ]; then
        git init -q
    fi
    if git remote get-url origin >/dev/null 2>&1; then
        git remote set-url origin '$FORK_URL'
    else
        git remote add origin '$FORK_URL'
    fi
    git fetch origin '$NAS_GIT_BRANCH'
    git checkout -B '$NAS_GIT_BRANCH' origin/'$NAS_GIT_BRANCH'
else
    git clone --branch '$NAS_GIT_BRANCH' '$FORK_URL' '$NAS_REPO_PATH'
fi

# Try to chown data dir to UID 1000 (matches the container's appuser).
# Synology's default user typically can't sudo without a password, so we
# attempt the chown directly and only warn if it fails.
chown -R 1000:1000 '$NAS_DATA_PATH' 2>/dev/null \\
    || echo '[deploy] note: could not chown $NAS_DATA_PATH to 1000:1000 — if the container fails to write, run: sudo chown -R 1000:1000 $NAS_DATA_PATH'
"

# Step 2 — make sure .env exists; if not, create from .example with a clear marker.
echo
echo "[deploy] ----- step 2: check .env -----"
"$NAS_CMD" "set -e
cd '$NAS_REPO_PATH'
if [ ! -f .env ]; then
    cp .env.example .env
    chmod 600 .env
    echo '----------------------------------------'
    echo '[deploy] CREATED .env from template.'
    echo '[deploy] Edit it on the NAS and add your API keys, then rerun deploy.sh:'
    echo '    nano $NAS_REPO_PATH/.env'
    echo '[deploy] Aborting deploy until .env is filled in.'
    echo '----------------------------------------'
    exit 10
fi
# Verify the .env has at least one API key set.
if ! grep -E '^(OPENAI|GOOGLE|ANTHROPIC|XAI|DEEPSEEK|DASHSCOPE|ZHIPU|OPENROUTER)_API_KEY=.+' .env >/dev/null; then
    echo '[deploy] WARNING: .env exists but no provider API key looks set. The GUI will start but every run will fail.'
fi
chmod 600 .env || true
echo '[deploy] .env present.'
"

# Step 3 — build the gui image
echo
echo "[deploy] ----- step 3: build gui image -----"
"$NAS_CMD" "cd '$NAS_REPO_PATH' && docker compose build gui"

# Step 4 — start the gui service
echo
echo "[deploy] ----- step 4: start gui -----"
"$NAS_CMD" "cd '$NAS_REPO_PATH' && docker compose up -d gui"

# Step 5 — wait for healthcheck + dump first 50 log lines
echo
echo "[deploy] ----- step 5: health + first logs -----"
"$NAS_CMD" "set -e
cd '$NAS_REPO_PATH'
echo '[deploy] waiting up to 90s for healthcheck…'
for i in \$(seq 1 30); do
    status=\$(docker inspect --format='{{.State.Health.Status}}' tradingagents-gui 2>/dev/null || echo missing)
    if [ \"\$status\" = healthy ]; then
        echo '[deploy] healthy after ~'\$((i * 3))'s'
        break
    fi
    sleep 3
done
echo
echo '[deploy] last 50 log lines:'
docker compose logs --tail=50 gui
"

cat <<EOF

[deploy] ----- done -----
Web UI: http://${NAS_HOST}:${TRADINGAGENTS_GUI_PORT:-8501}/

Next:
  1. Open the URL, go to **Settings**, paste at least one provider API key
     (it's stored in $NAS_REPO_PATH/data/gui_config.json with mode 0600).
  2. Run a test analysis from the **Run** page.
  3. For routine updates later, run: scripts/nas/upgrade.sh

EOF
