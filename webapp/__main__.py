"""``python -m webapp``: start the local web console.

Binds to the loopback address by default. ``TRADINGAGENTS_WEB_HOST`` /
``TRADINGAGENTS_WEB_PORT`` move it, and ``TRADINGAGENTS_WEB_RELOAD=1`` turns on
the development reloader. Binding to a non-local host is refused unless
``TRADINGAGENTS_WEB_ALLOW_REMOTE=1`` is set as well, since the API starts paid
model runs and serves report files off this machine's disk.
"""

from __future__ import annotations

import os
import sys

from tradingagents import __version__

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def startup_diagnostics() -> list[str]:
    """The lines a console prints so the running build is identifiable.

    The audit could not tell from outside whether the serving process ran the
    merged code: a process started before a deployment keeps its modules. The
    same identifiers `/api/health` returns are printed here, so the answer is
    in the console that started the process and needs no HTTP call.

    Never raises: a broken git checkout or an unimportable validator must not
    stop the server from starting, only make one line say ``unknown``.
    """
    try:
        from tradingagents.build_info import commit_sha
        from tradingagents.dataflows import run_record

        info = run_record.runtime_fingerprint()
        lines = [
            f"build {info['build_id']} (commit {commit_sha()}, python {info['python']})",
        ]
        broken = [name for name, status in (info.get("validators") or {}).items()
                  if not status.get("loaded")]
        if broken:
            lines.append("validators NOT loaded: " + ", ".join(sorted(broken)))
        else:
            lines.append("validators loaded: " + ", ".join(sorted(info.get("validators") or {})))
        return lines
    except Exception as exc:  # noqa: BLE001 — diagnostics never block a start
        return [f"build unknown ({type(exc).__name__}: {exc})"]



def main(argv: list[str] | None = None) -> int:
    """Run the server; returns the process exit code."""
    try:
        import uvicorn
    except ModuleNotFoundError:
        print(
            "The web console needs FastAPI and Uvicorn:\n"
            "    pip install 'fastapi>=0.115' 'uvicorn>=0.30'\n"
            "or install the extra:  pip install '.[web]'",
            file=sys.stderr,
        )
        return 1

    host = os.environ.get("TRADINGAGENTS_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("TRADINGAGENTS_WEB_PORT", "8000"))
    reload_enabled = os.environ.get("TRADINGAGENTS_WEB_RELOAD") == "1"
    allow_remote = os.environ.get("TRADINGAGENTS_WEB_ALLOW_REMOTE") == "1"

    if host not in LOCAL_HOSTS and not allow_remote:
        print(
            f"Refusing to bind to {host}: the console starts model runs and reads "
            "files on this machine. Set TRADINGAGENTS_WEB_ALLOW_REMOTE=1 to override.",
            file=sys.stderr,
        )
        return 2

    print(
        f"TradingAgents web console v{__version__}: http://{host}:{port}/  (Ctrl-C to stop)"
    )
    for line in startup_diagnostics():
        print(f"  {line}")
    uvicorn.run(
        "webapp.app:app",
        host=host,
        port=port,
        reload=reload_enabled,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
