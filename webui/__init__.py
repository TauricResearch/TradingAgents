"""Web UI for TradingAgents: a browser front end over the same graph the CLI runs.

Nothing here reimplements the pipeline. :mod:`webui.runs` drives
``TradingAgentsGraph`` exactly as ``cli/run.py`` does — same initial state, same
stream, same report tree — and turns the stream into events a browser can read.
:mod:`webui.store` adds the one thing the CLI has no home for: a portfolio that
persists between runs, so the book is entered once rather than passed as a file
on every invocation.
"""

__all__ = ["create_app"]


def create_app(*args, **kwargs):
    """Lazily build the FastAPI app so importing the package needs no FastAPI."""
    from webui.server import create_app as _create_app

    return _create_app(*args, **kwargs)
