"""
Backend module entry point
Run with: python -m backend
Options:
  --reload / --reload false  Enable/disable hot reload (default: true for dev)
  --port PORT                Server port (default: 8000)
  --host HOST                Server host (default: 0.0.0.0)
"""
import uvicorn
import os
import sys
import argparse
from pathlib import Path

# Add parent directory to path to import tradingagents
parent_dir = str(Path(__file__).parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="TradingAgentsX Backend Server")
    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("BACKEND_HOST", "0.0.0.0"),
        help="Server host (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", os.getenv("BACKEND_PORT", "8000"))),
        help="Server port (default: 8000)"
    )
    parser.add_argument(
        "--reload",
        type=str,
        default=os.getenv("BACKEND_RELOAD", "true"),
        help="Enable hot reload (true/false, default: true)"
    )
    return parser.parse_args()


def main():
    """Start the FastAPI server"""
    args = parse_args()
    
    # Parse reload flag (support both boolean-style and string)
    reload = args.reload.lower() in ("true", "1", "yes") if isinstance(args.reload, str) else args.reload
    
    print(f"🚀 Starting TradingAgentsX Backend Server...")
    print(f"📍 Host: {args.host}")
    print(f"🔌 Port: {args.port}")
    print(f"🔄 Reload: {reload}")
    print(f"\n📖 API Documentation: http://localhost:{args.port}/docs")
    print(f"📊 Health Check: http://localhost:{args.port}/api/health\n")
    
    # Start uvicorn server
    uvicorn.run(
        "backend.app.main:app",  # Use full module path
        host=args.host,
        port=args.port,
        reload=reload,
        reload_excludes=["frontend/*", "node_modules/*", "*.pyc", ".git/*"],
        log_level="info",
    )


if __name__ == "__main__":
    main()
