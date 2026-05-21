"""Convenience launcher for the Streamlit auth (login / register) page."""

import subprocess
import sys
from pathlib import Path

auth_path = Path(__file__).parent / "tradingbot" / "dashboard" / "auth_app.py"

if __name__ == "__main__":
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(auth_path),
        "--server.headless", "false",
        "--theme.base", "dark",
    ]
    subprocess.run(cmd)
