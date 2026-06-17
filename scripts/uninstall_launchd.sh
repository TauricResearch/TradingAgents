#!/usr/bin/env bash
# Remove the TradingAgents daily launchd job installed by install_launchd.sh.
# Safe to run when the job is not present; the plist file is deleted either way.

set -euo pipefail

LABEL="com.tradingagents.daily"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"

if launchctl list | grep -q "${LABEL}"; then
    launchctl unload "${PLIST_PATH}" 2>/dev/null || true
    echo "Unloaded ${LABEL}"
else
    echo "${LABEL} is not loaded; nothing to unload"
fi

if [[ -f "${PLIST_PATH}" ]]; then
    rm "${PLIST_PATH}"
    echo "Removed ${PLIST_PATH}"
fi
