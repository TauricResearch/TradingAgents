"""Make ``egta.evaluation`` importable without packaging ``src/``.

The project installs only ``tradingagents*`` and ``cli*`` (see
``pyproject.toml`` ``packages.find``); the EGTA application under ``src/`` is
wired into the build later (E3). Until then these offline contract tests put the
repo's ``src`` directory on ``sys.path`` so ``from egta.contracts ...`` imports
without modifying ``pyproject.toml``.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
