"""The research library's memory log, where a rerun's decision takes the place of the
one it replaced (#53)."""

from __future__ import annotations

from pathlib import Path

from tradingagents.dataflows.files import locked, replace_file
from tradingagents.memory.log import TradingMemoryLog


def replace_decision(log_path: Path, ticker: str, trade_date: str, decision: str, rating: str) -> bool:
    """Put a rerun's decision in place of the pending entry of ``ticker`` on ``trade_date``.

    The log keeps the first entry of a ticker's day (``store_decision``), and its
    settled entries are what the rating accuracy scores: without this, a rerun would
    be settled with the rating it replaced. False, and the log left as it is, when
    the day has no pending entry: none was stored, or it is settled already.
    """
    separator = TradingMemoryLog._SEPARATOR
    tag = f"[{trade_date} | {ticker} |"
    if not log_path.is_file():  # no log yet, maybe not even the directory its lock goes in
        return False
    with locked(log_path):
        blocks = log_path.read_text(encoding="utf-8").split(separator)
        day = next((i for i, block in enumerate(blocks) if block.lstrip().startswith(tag)), None)
        if day is None or not blocks[day].strip().splitlines()[0].endswith("| pending]"):
            return False
        del blocks[day]
        text = separator.join(blocks)
        replace_file(log_path, lambda temp: Path(temp).write_text(text, encoding="utf-8"))
    TradingMemoryLog({"memory_log_path": str(log_path)}).store_decision(ticker, trade_date, decision, rating)
    return True
