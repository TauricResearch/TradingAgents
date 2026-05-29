import json
import os
from pathlib import Path

PREFS_FILE = Path.home() / ".tradingagents" / "user_prefs.json"

def load_prefs():
    if PREFS_FILE.exists():
        try:
            with open(PREFS_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_prefs(prefs):
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PREFS_FILE, "w") as f:
        json.dump(prefs, f, indent=4)
