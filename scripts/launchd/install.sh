#!/usr/bin/env bash
# Install the Polymarket research engine as a daily launchd job (macOS).
#
# Default: runs once per day at 09:00 local time, 5 markets per run, Sonnet
# model, $100 paper budget per non-HOLD decision. Edit the .plist before
# running this script if you want different parameters.
#
# Usage:
#   bash scripts/launchd/install.sh           # install + load
#   bash scripts/launchd/install.sh --uninstall  # unload + remove
#   bash scripts/launchd/install.sh --status   # check if loaded

set -euo pipefail

LABEL="com.mingshum.polymarket"
SRC_PLIST="$(cd "$(dirname "$0")" && pwd)/${LABEL}.plist"
DEST_PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="$HOME/.tradingagents/polymarket"

if [[ "${1:-}" == "--uninstall" ]]; then
    if launchctl list "$LABEL" &>/dev/null; then
        launchctl unload "$DEST_PLIST"
        echo "Unloaded $LABEL."
    fi
    if [[ -f "$DEST_PLIST" ]]; then
        rm "$DEST_PLIST"
        echo "Removed $DEST_PLIST."
    fi
    exit 0
fi

if [[ "${1:-}" == "--status" ]]; then
    if launchctl list "$LABEL" &>/dev/null; then
        echo "Loaded:"
        launchctl list "$LABEL"
    else
        echo "Not loaded."
    fi
    if [[ -f "$LOG_DIR/launchd-stdout.log" ]]; then
        echo
        echo "Recent stdout (last 20 lines):"
        tail -20 "$LOG_DIR/launchd-stdout.log"
    fi
    exit 0
fi

# Default: install + load
mkdir -p "$LOG_DIR"
mkdir -p "$(dirname "$DEST_PLIST")"

if [[ -f "$DEST_PLIST" ]]; then
    echo "Existing plist found at $DEST_PLIST"
    if launchctl list "$LABEL" &>/dev/null; then
        echo "  Unloading current instance..."
        launchctl unload "$DEST_PLIST"
    fi
fi

cp "$SRC_PLIST" "$DEST_PLIST"
echo "Copied plist to $DEST_PLIST"

launchctl load "$DEST_PLIST"
echo "Loaded $LABEL."

echo
echo "Daily run scheduled at 09:00 local time."
echo "Logs: $LOG_DIR/launchd-stdout.log"
echo "      $LOG_DIR/launchd-stderr.log"
echo
echo "Useful commands:"
echo "  bash scripts/launchd/install.sh --status     # check status"
echo "  bash scripts/launchd/install.sh --uninstall  # remove"
echo "  launchctl start $LABEL                       # trigger now (one-off)"
