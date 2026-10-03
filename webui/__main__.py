"""``python -m webui``: serve the UI on the loopback interface."""

from __future__ import annotations

import argparse

from webui.serve import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the TradingAgents web UI.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Interface to bind. Defaults to loopback; the server has no auth.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser.")
    args = parser.parse_args()
    serve(host=args.host, port=args.port, open_browser=not args.no_open)


if __name__ == "__main__":
    main()
