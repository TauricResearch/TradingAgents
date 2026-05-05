#!/usr/bin/env python3
"""Check all server files are under MAX_LINES lines."""

import os
import sys
import subprocess

MAX_LINES = int(os.environ.get("MAX_LINES", "300"))

result = subprocess.run(
    ["find", "server", "-name", "*.ts", "-o", "-name", "*.tsx"],
    capture_output=True, text=True
)
files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

violators = []
for f in files:
    try:
        lines = len(open(f).readlines())
    except Exception:
        continue
    if lines > MAX_LINES:
        violators.append((lines, f))

if violators:
    violators.sort(reverse=True)
    print(f"  ✗ Files exceeding {MAX_LINES} lines:")
    for lines, path in violators:
        print(f"    {lines:4d}  {path}")
    print()
    sys.exit(1)
else:
    print(f"  ✓ All {len(files)} server files are {MAX_LINES} lines or under")
    sys.exit(0)