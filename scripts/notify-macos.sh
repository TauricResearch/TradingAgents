#!/usr/bin/env bash
set -euo pipefail

msg="${1:-Done}"
title="${2:-Claude Code}"

if command -v terminal-notifier >/dev/null 2>&1; then
    terminal-notifier -title "$title" -message "$msg" -group "claude-code" -sound default
elif command -v osascript >/dev/null 2>&1; then
    # Fallback to osascript if terminal-notifier is not installed
    osascript -e "display notification \"$msg\" with title \"$title\""
else
    echo "⚠️ No notification system available. Message: $msg"
fi