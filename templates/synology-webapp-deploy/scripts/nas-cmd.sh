#!/usr/bin/env bash
# Run a command on the NAS over SSH. Reads connection info from
# scripts/nas/credentials.local — that file is git-ignored and never
# touched by Claude directly.
#
# Wraps remote commands in ``bash -lc`` so non-interactive SSH sessions
# pick up the user's PATH (Synology's default PATH excludes
# /usr/local/bin where docker lives).
#
# Usage:
#     scripts/nas/nas-cmd.sh "<command>"

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRED_FILE="$DIR/credentials.local"

if [[ ! -f "$CRED_FILE" ]]; then
    cat >&2 <<EOF
[nas-cmd] Missing $CRED_FILE.
Copy from credentials.local.example and fill in NAS_HOST, NAS_USER,
plus EITHER NAS_SSH_KEY or NAS_PASSWORD.
EOF
    exit 2
fi

# shellcheck disable=SC1090
source "$CRED_FILE"

: "${NAS_HOST:?NAS_HOST not set in credentials.local}"
: "${NAS_USER:?NAS_USER not set in credentials.local}"
NAS_SSH_PORT="${NAS_SSH_PORT:-22}"

REMOTE_CMD="${1:-true}"

# Wrap in login shell so /etc/profile + the user's profile fragments
# get sourced. Synology's default non-interactive PATH excludes
# /usr/local/bin where docker lives.
WRAPPED_CMD="bash -lc $(printf %q "$REMOTE_CMD")"

ssh_opts=(
    -p "$NAS_SSH_PORT"
    -o StrictHostKeyChecking=accept-new
    -o ServerAliveInterval=30
    -o ConnectTimeout=10
    -tt
)

if [[ -n "${NAS_SSH_KEY:-}" ]]; then
    NAS_SSH_KEY_EXPANDED="${NAS_SSH_KEY/#\~/$HOME}"
    [[ -f "$NAS_SSH_KEY_EXPANDED" ]] || {
        echo "[nas-cmd] SSH key not found: $NAS_SSH_KEY" >&2
        exit 3
    }
    exec ssh -i "$NAS_SSH_KEY_EXPANDED" "${ssh_opts[@]}" \
        "$NAS_USER@$NAS_HOST" "$WRAPPED_CMD"
elif [[ -n "${NAS_PASSWORD:-}" ]]; then
    if ! command -v sshpass >/dev/null 2>&1; then
        cat >&2 <<EOF
[nas-cmd] Password auth requires sshpass on the local machine.
Install: apt install sshpass / brew install hudochenkov/sshpass/sshpass / scoop install sshpass.
Or — recommended — switch to NAS_SSH_KEY auth.
EOF
        exit 4
    fi
    exec sshpass -p "$NAS_PASSWORD" ssh "${ssh_opts[@]}" \
        "$NAS_USER@$NAS_HOST" "$WRAPPED_CMD"
else
    echo "[nas-cmd] Set either NAS_SSH_KEY or NAS_PASSWORD in credentials.local" >&2
    exit 5
fi
