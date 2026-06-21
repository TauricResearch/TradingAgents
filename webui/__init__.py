# TradingAgents Web UI

import sys
import subprocess
from pathlib import Path


def main():
    """Entry point for the tradingagents-webui command."""
    app_path = Path(__file__).resolve().parent / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path)], check=True)
