#!/usr/bin/env python3
"""
Convert all onclick="FUNC(args)" with variable interpolation in dynamically-
generated HTML strings to use data attributes + event delegation.

Problem: onclick="FUNC(' + var + ')" inside a JS string has escaping recursion.
Fix: data-action="FUNC" data-var="value" + one delegation handler.
"""

import re

# ── Mapping: old onclick → data attributes needed ──────────────────────────
# Each entry: (pattern_regex, replacement_template)
# Groups: (1)=func name (2..N)=var names

REPLACEMENTS = [
    # analyzeTicker(ticker)
    (
        r'onclick="analyzeTicker\(\\\'\\\' \+ (\w+) \+ \\\'\\\'\)"',
        r'data-action="analyzeTicker" data-ticker="\1"'
    ),
    # closePosition(id)
    (
        r'onclick="closePosition\(\\\'\\\' \+ (\w+) \+ \\\'\\\'\)"',
        r'data-action="closePosition" data-id="\1"'
    ),
    # createExitPlan(ticker, platform)  [two args]
    (
        r'onclick="createExitPlan\(\\\'\\\' \+ (\w+) \+ \\\'\\\'\,\\\'\\\' \+ (\w+) \+ \\\'\\\'\)"',
        r'data-action="createExitPlan" data-ticker="\1" data-platform="\2"'
    ),
    # viewPostMortem(ticker) / reanalyzeTicker(ticker)
    (
        r'onclick="(viewPostMortem|reanalyzeTicker)\(\\\'\\\' \+ (\w+) \+ \\\'\\\'\)"',
        r'data-action="\1" data-ticker="\2"'
    ),
    # loadAnalysisCard(ticker, date)
    (
        r'onclick="loadAnalysisCard\(\\\'\\\' \+ (\w+) \+ \\\'\\\'\,\\\'\\\' \+ (\w+) \+ \\\'\\\'\)"',
        r'data-action="loadAnalysisCard" data-ticker="\1" data-date="\2"'
    ),
    # explainAnalysis(ticker, date) / showAnalysisFull(ticker, date)
    (
        r'onclick="(explainAnalysis|showAnalysisFull)\(\\\'\\\' \+ (\w+) \+ \\\'\\\'\,\\\'\\\' \+ (\w+) \+ \\\'\\\'\)"',
        r'data-action="\1" data-ticker="\2" data-date="\3"'
    ),
    # advanceStage(id, stage)  [numeric id, string stage]
    (
        r'onclick="advanceStage\(\' \+ (\w+) \+ \'\, \\\'\\\' \+ (\w+) \+ \\\'\\\'\)"',
        r'data-action="advanceStage" data-id="\1" data-stage="\2"'
    ),
    # removeProspect(id)  [numeric id only]
    (
        r'onclick="removeProspect\(\' \+ (\w+) \+ \'\)"',
        r'data-action="removeProspect" data-id="\1"'
    ),
]


def fix_file(path: str) -> None:
    with open(path) as f:
        content = f.read()

    orig = content
    total = 0

    for pattern, replacement in REPLACEMENTS:
        new_content = re.sub(pattern, replacement, content)
        count = len(re.findall(pattern, content))
        if count:
            print(f"  {path}: {count}x → {replacement[:50]}")
        content = new_content

    if content != orig:
        with open(path, 'w') as f:
            f.write(content)
        print(f"  WROTE {path}")


if __name__ == "__main__":
    files = [
        "server/views/workflow.tsx",
        "server/views/history.tsx",
        "server/views/holdings.tsx",
        "server/views/prospects.tsx",
    ]
    for f in files:
        print(f"\nFixing {f}...")
        fix_file(f)
    print("\nDone.")