#!/usr/bin/env bash
# Run a command on the NAS over SSH. Reads connection info from
# scripts/nas/credentials.local — that file is git-ignored and never
# touched by Claude directly. Source of truth for "how Claude reaches
# the NAS" is this script.
#
# Usage:
#     scripts/nas/nas-cmd.sh "<command-string>"
#
# Examples:
#     scripts/nas/nas-cmd.sh 'docker compose ps'
#     scripts/nas/nas-cmd.sh 'docker compose logs --tail=50 gui'

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRED_FILE="$DIR/credentials.local"

if [[ ! -f "$CRED_FILE" ]]; then
    cat >&2 <<EOF
[nas-cmd] Missing $CRED_FILE.
Create it from credentials.local.example:

    cp scripts/nas/credentials.local.example scripts/nas/credentials.local
    # then edit credentials.local and fill in NAS_HOST, NAS_USER,
    # plus EITHER NAS_SSH_KEY or NAS_PASSWORD.
EOF
    exit 2
fi

# shellcheck disable=SC1090
source "$CRED_FILE"

: "${NAS_HOST:?NAS_HOST not set in credentials.local}"
: "${NAS_USER:?NAS_USER not set in credentials.local}"
NAS_SSH_PORT="${NAS_SSH_PORT:-22}"
NAS_REPO_PATH="${NAS_REPO_PATH:-/volume1/docker/tradingagents}"

# Wrap command with a cd into the repo so most invocations don't need to.
REMOTE_CMD="${1:-true}"

ssh_opts=(
    -p "$NAS_SSH_PORT"
    -o StrictHostKeyChecking=accept-new
    -o ServerAliveInterval=30
    -o ConnectTimeout=10
    -tt   # request a TTY; some Synology shells need it for docker output
)

if [[ -n "${NAS_SSH_KEY:-}" ]]; then
    # Expand ~ if the user typed a tilde-prefixed path.
    NAS_SSH_KEY_EXPANDED="${NAS_SSH_KEY/#\~/$HOME}"
    [[ -f "$NAS_SSH_KEY_EXPANDED" ]] || {
        echo "[nas-cmd] SSH key not found: $NAS_SSH_KEY" >&2
        exit 3
    }
    exec ssh -i "$NAS_SSH_KEY_EXPANDED" "${ssh_opts[@]}" \
        "$NAS_USER@$NAS_HOST" "$REMOTE_CMD"
elif [[ -n "${NAS_PASSWORD:-}" ]]; then
    if ! command -v sshpass >/dev/null 2>&1; then
        cat >&2 <<EOF
[nas-cmd] Password auth requires sshpass on the local machine.
Install one of:
  - WSL/Linux: sudo apt install sshpass
  - macOS:     brew install hudochenkov/sshpass/sshpass
  - Git Bash:  use scoop ('scoop install sshpass') or run from WSL
Or — recommended — switch to NAS_SSH_KEY auth.
EOF
        exit 4
    fi
    exec sshpass -p "$NAS_PASSWORD" ssh "${ssh_opts[@]}" \
        "$NAS_USER@$NAS_HOST" "$REMOTE_CMD"
else
    echo "[nas-cmd] Set either NAS_SSH_KEY or NAS_PASSWORD in credentials.local" >&2
    exit 5
fi
