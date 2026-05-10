#!/bin/sh
# Ensure appuser owns the data directory even when a named/bind volume
# mounts over it with different ownership (common on first run or when the
# host UID differs). After fixing ownership, drop privileges to appuser and
# exec the tradingagents CLI.
set -e

DATA_DIR="/home/appuser/.tradingagents"

# Create expected subdirs idempotently (cheap no-ops if they exist)
mkdir -p "$DATA_DIR/cache" "$DATA_DIR/logs" "$DATA_DIR/memory" 2>/dev/null || true

# Fix ownership. Silently ignore failures (e.g. read-only mounts) — the
# app will surface a clearer error if it still cannot write.
chown -R appuser:appuser "$DATA_DIR" 2>/dev/null || true

exec gosu appuser tradingagents "$@"
