#!/usr/bin/env bash
# Install the TradingAgents daily runner as a per-user launchd job.
#
# Creates ~/Library/LaunchAgents/com.tradingagents.daily.plist that fires
# Monday-Friday at 07:00 local time and runs scripts/run_daily.py with
# the project's virtualenv interpreter. Logs land in
# ~/Library/Logs/tradingagents/.
#
# Idempotent: re-running replaces the existing plist and reloads the
# job, so it's safe to use as a deployment step.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="${PROJECT_ROOT}/.venv/bin/python"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
LOG_DIR="${HOME}/Library/Logs/tradingagents"
PLIST_PATH="${LAUNCH_AGENTS_DIR}/com.tradingagents.daily.plist"
LABEL="com.tradingagents.daily"

if [[ ! -x "${VENV_PY}" ]]; then
    echo "error: ${VENV_PY} not found or not executable." >&2
    echo "       Create the project venv first: uv venv .venv && .venv/bin/pip install -e '.[scheduled]'" >&2
    exit 1
fi

mkdir -p "${LAUNCH_AGENTS_DIR}" "${LOG_DIR}"

# Unload any prior copy so launchd doesn't keep a stale process around.
if launchctl list | grep -q "${LABEL}"; then
    launchctl unload "${PLIST_PATH}" 2>/dev/null || true
fi

cat > "${PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${VENV_PY}</string>
        <string>${PROJECT_ROOT}/scripts/run_daily.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_ROOT}</string>

    <!-- Mon-Fri at 07:00 local time. launchd uses the system time zone. -->
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
    </array>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/run_daily.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/run_daily.err.log</string>

    <!-- launchd throttles the job on a 10s interval if it exits too
         quickly; we don't care, but ProcessType=Background keeps it
         off the "responsive app" radar. -->
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
EOF

# Validate before loading — `plutil` is bundled with macOS.
if ! plutil -lint "${PLIST_PATH}" >/dev/null; then
    echo "error: generated plist failed plutil validation" >&2
    cat "${PLIST_PATH}" >&2
    exit 1
fi

launchctl load -w "${PLIST_PATH}"

echo "Installed launchd job: ${LABEL}"
echo "  plist: ${PLIST_PATH}"
echo "  logs:  ${LOG_DIR}/"
echo "  verify: launchctl list | grep ${LABEL}"
echo "  trigger now: launchctl start ${LABEL}"
