"""Entry point: python -m web [--dev] [--host HOST] [--port PORT]"""
import argparse
import os
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(description="TradingAgents Web UI")
    parser.add_argument("--dev", action="store_true", help="Enable CORS for Vite dev server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()

    if args.dev:
        os.environ["TRADINGAGENTS_WEB_DEV"] = "1"

    import uvicorn

    url = f"http://{args.host}:{args.port}"
    print(f"TradingAgents Web UI → {url}")
    if not args.dev:
        webbrowser.open(url)

    uvicorn.run(
        "web.server:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
