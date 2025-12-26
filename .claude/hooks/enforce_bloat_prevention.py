#!/usr/bin/env python3
"""Enforce simplicity and prevent bloat from returning.

Blocks commits if:
- Documentation files exceed limits
- Agents grow too large (trust the model)
- Commands exceed limits
- Python infrastructure sprawls
- Net growth without cleanup
"""

import subprocess
import sys
from pathlib import Path


def count_files(pattern: str) -> int:
    """Count files matching pattern."""
    result = subprocess.run(
        ["find", ".", "-path", pattern, "-type", "f"],
        capture_output=True,
        text=True
    )
    return len([l for l in result.stdout.strip().split("\n") if l])


def count_lines(pattern: str) -> int:
    """Count lines in files matching pattern."""
    result = subprocess.run(
        ["find", ".", "-path", pattern, "-type", "f", "-name", "*.md"],
        capture_output=True,
        text=True
    )
    files = [l for l in result.stdout.strip().split("\n") if l]
    if not files:
        return 0

    total = 0
    for f in files:
        try:
            with open(f) as fp:
                total += len(fp.readlines())
        except:
            pass
    return total


def main():
    """Check bloat prevention rules."""
    errors = []
    warnings = []

    # Rule 1: Docs files
    docs_count = count_files("./docs -not -path */archive")
    plugin_docs_count = count_files("./plugins/autonomous-dev/docs -not -path */archive")
    total_docs = docs_count + plugin_docs_count

    if total_docs > 35:
        errors.append(f"❌ Documentation bloat: {total_docs} files (limit: 35)")
    elif total_docs > 30:
        warnings.append(f"⚠️  Documentation approaching limit: {total_docs} files")

    # Rule 2: Agent lines
    agent_lines = count_lines("./plugins/autonomous-dev/agents")
    if agent_lines > 1500:
        errors.append(f"❌ Agents too large: {agent_lines} total lines (limit: 1500)")
    elif agent_lines > 1400:
        warnings.append(f"⚠️  Agents approaching limit: {agent_lines} lines")

    # Rule 3: Commands
    commands = count_files("./plugins/autonomous-dev/commands -not -path */archive")
    if commands > 8:
        errors.append(f"❌ Too many commands: {commands} (limit: 8)")
        errors.append("   Allowed: auto-implement, align-project, setup, test, status, health-check, sync-dev, uninstall")

    # Rule 4: Python modules
    lib_modules = len(list(Path("./plugins/autonomous-dev/lib").glob("*.py")))
    if lib_modules > 25:
        errors.append(f"❌ Python infrastructure sprawl: {lib_modules} modules (limit: 25)")
    elif lib_modules > 20:
        warnings.append(f"⚠️  Python modules approaching limit: {lib_modules}")

    # Report
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print("\n💡 To fix bloat:", file=sys.stderr)
        print("   1. Archive old documentation files", file=sys.stderr)
        print("   2. Simplify agents (trust the model more)", file=sys.stderr)
        print("   3. Archive redundant commands", file=sys.stderr)
        print("   4. Consolidate Python modules", file=sys.stderr)
        sys.exit(2)

    if warnings:
        for warning in warnings:
            print(warning, file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
