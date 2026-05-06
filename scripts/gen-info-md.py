#!/usr/bin/env python3
"""Generate docs/info.md with current project state."""

import os
import subprocess
from datetime import datetime, timezone


def sh(cmd: str, default: str = "unknown") -> str:
    try:
        return subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        return default


def query_db(sql: str, default: str = "unknown") -> str:
    try:
        db_path = os.environ.get("PORTFOLIO_DB", "portfolio.db")
        result = subprocess.run(
            ["sqlite3", db_path, sql], capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else default
    except Exception:
        return default


branch = sh("git branch --show-current")
openrouter = "✓ set" if os.environ.get("OPENROUTER_API_KEY") else "✗ not set"
tools = f"  just      {sh('just --version', '?')}\n  bun       {sh('bun --version', '?')}\n  uv        {sh('uv --version', '?')}\n  python    {sh('python3 --version', '?')}"

db_signals = query_db("SELECT COUNT(*) FROM signals")
db_positions = query_db("SELECT COUNT(*) FROM positions")
db_analyses = query_db("SELECT COUNT(*) FROM analyses")
db_watchlist = query_db("SELECT COUNT(*) FROM watchlist")

td_status = sh("td current 2>/dev/null | head -12", "no td session")

debriefs = sh("ls -t debriefs/*.md 2>/dev/null | head -3 | tr '\\n' ',' | sed 's/,$//' || echo 'none'")
debriefs = "  ".join(debriefs.split(",")) if debriefs else "none"
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

print(f"""# TradingAgents — Current State

_generated: {now}_

## Git
```
Branch: {branch}
```

## Tools
```
{tools}
```

## Environment
```
OPENROUTER_API_KEY  {openrouter}
HLEDGER_FILE        {os.environ.get('HLEDGER_FILE', '~/.hledger.journal')}
PORTFOLIO_DB        {os.environ.get('PORTFOLIO_DB', './portfolio.db')}
TA_DASHBOARD_PORT   {os.environ.get('TA_DASHBOARD_PORT', '3000')}
```

## Database (DEV)
```
signals    {db_signals}
positions  {db_positions}
analyses   {db_analyses}
watchlist  {db_watchlist}
```

## Active session
```
{td_status}
```

## Recent debriefs
```
{debriefs}
```
""")