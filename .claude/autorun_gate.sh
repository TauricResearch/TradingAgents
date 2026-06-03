#!/usr/bin/env bash
# SessionStart gate for TradingAgents report top-up.
# Invoked from the GLOBAL Claude hook (~/.claude/settings.json) by path.
# Only runs Mon-Fri, 7:00 PM or later, Pacific time. Always exits 0 so it
# never blocks session start.

set -u

REPO="/Users/bichengwang/my-code/other/TradingAgents"

dow=$(TZ=America/Los_Angeles date +%u)   # 1=Mon .. 7=Sun
hour=$(TZ=America/Los_Angeles date +%H)  # 00..23

if [ "$dow" -le 5 ] && [ "$hour" -ge 19 ]; then
  {
    cd "$REPO" \
      && mkdir -p /tmp/ta_runlogs \
      && mkdir "/tmp/ta_autorun_$(date +%F).lock" 2>/dev/null \
      && nohup bash .claude/run_missing_today.sh \
           > "/tmp/ta_runlogs/autorun_$(date +%F).log" 2>&1
  } &
fi

exit 0
