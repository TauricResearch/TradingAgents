#!/usr/bin/env bash
# First-time deploy of a project to the Synology NAS.
#
# What this does on the NAS:
#   1. mkdir -p NAS_REPO_PATH and clone (or fetch+checkout) the project
#   2. mkdir -p NAS_DATA_PATH and chown to UID:GID 1000:1000
#   3. ensure .env exists at the project root (creating from .env.example
#      and aborting if it's still empty)
#   4. docker compose build $DEPLOY_SERVICES
#   5. docker compose up -d $DEPLOY_SERVICES
#   6. wait for healthchecks and tail logs
#
# Idempotent: safe to run multiple times. Re-running pulls + rebuilds
# instead of cloning. .env is never overwritten.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$DIR/_lib.sh"

echo "[deploy] project:    $PROJECT_NAME"
echo "[deploy] target NAS: $NAS_USER@$NAS_HOST"
echo "[deploy] repo path:  $NAS_REPO_PATH"
echo "[deploy] data path:  $NAS_DATA_PATH"
echo "[deploy] services:   $DEPLOY_SERVICES"
echo "[deploy] git:        $FORK_URL @ $NAS_GIT_BRANCH"
echo

# Step 1 — clone or pull, set up data dir
echo "[deploy] ----- step 1: clone + set up paths -----"
"$NAS_CMD" "set -e
mkdir -p '$NAS_REPO_PATH' '$NAS_DATA_PATH'

if [ -d '$NAS_REPO_PATH/.git' ]; then
    cd '$NAS_REPO_PATH'
    git fetch --all --prune
    git checkout '$NAS_GIT_BRANCH'
    git pull --ff-only
elif [ -d '$NAS_REPO_PATH' ]; then
    # Existing dir (often containing only data/) but no .git — init in-place.
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

# Container's appuser runs as UID 1000 by convention. Try to chown
# the data dir so bind-mount writes work; warn if we don't have perms.
chown -R 1000:1000 '$NAS_DATA_PATH' 2>/dev/null \\
    || echo '[deploy] note: could not chown $NAS_DATA_PATH to 1000:1000 — if the container fails to write, run: sudo chown -R 1000:1000 $NAS_DATA_PATH'
"

# Step 2 — make sure .env exists with at least one provider key set
echo
echo "[deploy] ----- step 2: check .env -----"
"$NAS_CMD" "set -e
cd '$NAS_REPO_PATH'
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        chmod 600 .env
        echo '----------------------------------------'
        echo '[deploy] CREATED .env from template.'
        echo '[deploy] Edit on NAS, fill in secrets, then rerun deploy.sh:'
        echo '    nano $NAS_REPO_PATH/.env'
        echo '----------------------------------------'
        exit 10
    else
        echo '[deploy] WARNING: no .env or .env.example present. Continuing — your project may not need one.'
    fi
fi
chmod 600 .env 2>/dev/null || true
echo '[deploy] .env present.'
"

# Step 3 — build images
echo
echo "[deploy] ----- step 3: build $DEPLOY_SERVICES -----"
"$NAS_CMD" "cd '$NAS_REPO_PATH' && docker compose build $DEPLOY_SERVICES"

# Step 4 — start services
echo
echo "[deploy] ----- step 4: up $DEPLOY_SERVICES -----"
"$NAS_CMD" "cd '$NAS_REPO_PATH' && docker compose up -d $DEPLOY_SERVICES"

# Step 5 — health + first logs
echo
echo "[deploy] ----- step 5: health + first logs -----"
"$NAS_CMD" "set -e
cd '$NAS_REPO_PATH'
for c in $PRIMARY_CONTAINERS; do
    echo \"[deploy] waiting up to 120s for \$c healthcheck…\"
    for i in \$(seq 1 40); do
        status=\$(docker inspect --format='{{.State.Health.Status}}' \"\$c\" 2>/dev/null || echo missing)
        if [ \"\$status\" = healthy ]; then
            echo \"[deploy]   \$c healthy after ~\$((i * 3))s\"
            break
        fi
        if [ \"\$status\" = missing ]; then
            echo \"[deploy]   \$c not running yet (or no healthcheck declared)\"
            break
        fi
        sleep 3
    done
done
echo
for s in $DEPLOY_SERVICES; do
    echo \"[deploy] last 25 log lines (\$s):\"
    docker compose logs --tail=25 \"\$s\" || true
    echo
done
"

cat <<EOF

[deploy] ----- done -----
${PUBLIC_URL:+Web UI: $PUBLIC_URL}
${API_DOCS_URL:+API:    $API_DOCS_URL}

Next:
  1. Hit the URL(s) above and confirm the app responds.
  2. For routine updates: scripts/nas/upgrade.sh

EOF
