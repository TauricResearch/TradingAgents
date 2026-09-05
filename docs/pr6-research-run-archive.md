# PR6: Research Run Archive

The local artifact cache now has two roles:

- `prices/`, `fundamentals/`, `news/`, and `agent_outputs/` retain normalized
  current research inputs;
- `runs/<SYMBOL>/` retains immutable JSON snapshots of complete
  `ResearchReportBundle` results.

Each run archive captures the timestamped report bundle as it was evaluated,
including a supplied signal, its deterministic risk review, and its backtest.
It is therefore possible to review a historical decision without re-fetching
data or re-running an agent.

`run_ticker_research` accepts an optional `ResearchRunArchive`. The local CLI
automatically creates `JsonResearchRunArchive` when `--cache-dir` is supplied.
The local cockpit reads the latest valid archived bundle from that same cache
directory. Corrupted archived files are ignored so one bad snapshot cannot
break cockpit startup.

This is deliberately a local filesystem implementation. It establishes the
archive contract before a future SQLite or cloud synchronization layer, while
leaving the original TradingAgents graph untouched.
