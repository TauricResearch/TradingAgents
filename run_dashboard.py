"""Convenience launcher for the Streamlit dashboard."""

import subprocess
import sys
from pathlib import Path

dashboard_path = Path(__file__).parent / "tradingbot" / "dashboard" / "app.py"

if __name__ == "__main__":
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(dashboard_path),
        "--server.headless", "false",
        "--theme.base", "dark",
    ]
    subprocess.run(cmd)
