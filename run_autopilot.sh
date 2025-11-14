#!/bin/bash
VENV=/Users/slavanikitin/Documents/Projects/TradingAgents/.venv
if [ -d "$VENV" ]; then
  source "$VENV/bin/activate"
fi
PYTHONPATH="$VENV/lib/python3.13/site-packages:$PYTHONPATH" python3 main.py --autopilot
