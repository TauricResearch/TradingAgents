"""The saved portfolio: one book, on disk, edited from the browser.

The CLI takes a portfolio as a JSON file on each invocation. A UI needs the
book to outlive the run, so it is kept at a single path and read back whenever a
run starts. The file is the same shape ``--portfolio`` accepts, so the two entry
points stay interchangeable: a book saved here runs from the CLI unchanged.

The distinction :mod:`tradingagents.portfolio` draws is preserved end to end —
no saved file means no portfolio context at all, which is not the same as a
saved file holding an empty position list (a flat book). Deleting the book, not
emptying it, is how a user goes back to un-situated advice.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from tradingagents.portfolio import PortfolioContext


def portfolio_path(config: dict | None = None) -> Path:
    """Where the book lives: ``TRADINGAGENTS_PORTFOLIO_PATH``, else beside the memory log."""
    override = os.getenv("TRADINGAGENTS_PORTFOLIO_PATH")
    if override:
        return Path(override).expanduser()
    home = Path(os.path.expanduser("~")) / ".tradingagents"
    if config and config.get("memory_log_path"):
        # Follow wherever the run's own state is kept, so a relocated data
        # directory (Docker's volume, a test's temp dir) takes the book with it.
        home = Path(config["memory_log_path"]).expanduser().parent.parent
    return home / "portfolio.json"


def load(config: dict | None = None) -> PortfolioContext | None:
    """The saved book, or ``None`` when none has been saved.

    A corrupt file reads as no book rather than raising: the UI's first action
    would otherwise be an error page with no way to overwrite the bad file.
    """
    path = portfolio_path(config)
    if not path.exists():
        return None
    try:
        return PortfolioContext.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def save(portfolio: PortfolioContext, config: dict | None = None) -> Path:
    """Write the book atomically, so an interrupted save cannot truncate it."""
    path = portfolio_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".portfolio-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(portfolio.model_dump_json(indent=2))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def clear(config: dict | None = None) -> bool:
    """Delete the book, returning whether there was one. Runs go back to no portfolio context."""
    path = portfolio_path(config)
    existed = path.exists()
    path.unlink(missing_ok=True)
    return existed
