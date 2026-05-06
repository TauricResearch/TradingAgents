# Shared bootstrap for the deploy scripts. Sourced from the others.
# Loads project metadata + credentials and exposes:
#   PROJECT_NAME, NAS_REPO_PATH, NAS_DATA_PATH, FORK_URL,
#   NAS_GIT_REMOTE, NAS_GIT_BRANCH, DEPLOY_SERVICES,
#   DEFAULT_LOG_SERVICE, PRIMARY_CONTAINERS, PUBLIC_URL, API_DOCS_URL
# plus NAS_HOST / NAS_USER / NAS_SSH_PORT / etc. via credentials.local.

# This file is sourced — don't ``set -e`` here, the caller controls that.

DIR_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ENV="$DIR_LIB/synology-deploy.env"
CRED_FILE="$DIR_LIB/credentials.local"

if [[ ! -f "$PROJECT_ENV" ]]; then
    echo "[deploy] Missing $PROJECT_ENV." >&2
    echo "        Copy synology-deploy.env.example into scripts/nas/ and fill in." >&2
    exit 2
fi
# shellcheck disable=SC1090
source "$PROJECT_ENV"

if [[ ! -f "$CRED_FILE" ]]; then
    echo "[deploy] Missing $CRED_FILE." >&2
    echo "        Copy credentials.local.example into scripts/nas/credentials.local and fill in." >&2
    exit 2
fi
# shellcheck disable=SC1090
source "$CRED_FILE"

: "${PROJECT_NAME:?PROJECT_NAME not set in synology-deploy.env}"
: "${NAS_REPO_PATH:?NAS_REPO_PATH not set}"
: "${NAS_HOST:?NAS_HOST not set in credentials.local}"
: "${NAS_USER:?NAS_USER not set in credentials.local}"

NAS_DATA_PATH="${NAS_DATA_PATH:-$NAS_REPO_PATH/data}"
NAS_GIT_REMOTE="${NAS_GIT_REMOTE:-origin}"
NAS_GIT_BRANCH="${NAS_GIT_BRANCH:-main}"
DEPLOY_SERVICES="${DEPLOY_SERVICES:-}"
DEFAULT_LOG_SERVICE="${DEFAULT_LOG_SERVICE:-${DEPLOY_SERVICES%% *}}"
PRIMARY_CONTAINERS="${PRIMARY_CONTAINERS:-}"

NAS_CMD="$DIR_LIB/nas-cmd.sh"
[[ -x "$NAS_CMD" ]] || chmod +x "$NAS_CMD"
