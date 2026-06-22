"""Container entry point: ``desk-server`` (runs uvicorn).

Host/port/data-dir come from env so the compose service and the macOS app can
configure them. Binds 0.0.0.0 inside the container; the published port is mapped
to 127.0.0.1 on the host so it is never exposed off-box.
"""

from __future__ import annotations

import os


def main() -> int:
    # Prepare engine env (no dotenv; redirect data dirs) before anything imports
    # tradingagents transitively via the app module.
    from desk_adapter.env import prepare_environment

    prepare_environment(os.environ.get("DESK_BASE_DIR"))

    import uvicorn

    host = os.environ.get("DESK_SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("DESK_SERVER_PORT", "8765"))
    uvicorn.run("desk_server.app:app", host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
