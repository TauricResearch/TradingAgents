"""Batch-normalize heading levels across all ``docs/*/*/complete_report.md``.

The actual transform now lives in the shipped ``cli.report_headings`` module
(so it's importable in the Docker/site-packages layout where the CLI runs).
This script stays as the repo-local batch entry point that walks ``docs/`` and
rewrites every report in place; ``transform`` is re-exported for backward
compatibility (e.g. the test suite).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the repo root importable when run as ``python scripts/prune_report_headings.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.report_headings import transform  # noqa: E402  (re-exported)

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def main() -> int:
    targets = sorted(DOCS.glob("*/*/complete_report.md"))
    changed = 0
    for path in targets:
        original = path.read_text(encoding="utf-8")
        updated = transform(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
    print(f"Processed {len(targets)} reports; rewrote {changed}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
