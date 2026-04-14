"""Ticker universe — single source of truth.

All scanners that need a list of tickers should call load_universe(config).
Do NOT hardcode "data/tickers.txt" in scanner files — import this module instead.

Priority order:
  1. config["discovery"]["universe"] — explicit list (tests / overrides)
  2. config["tickers_file"]          — path from top-level config
  3. Default: data/tickers.txt resolved relative to repo root
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)

# Resolved once at import time — works regardless of cwd
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_TICKERS_FILE = str(_REPO_ROOT / "data" / "tickers.txt")


def load_universe(config: Optional[Dict[str, Any]] = None) -> List[str]:
    """Return the full ticker universe as a list of uppercase strings.

    Args:
        config: Top-level app config dict. If None, falls back to default file.

    Returns:
        Deduplicated list of ticker symbols in the order they appear in the file.
    """
    cfg = config or {}

    # 1. Explicit list in config (useful for tests or targeted overrides)
    explicit = cfg.get("discovery", {}).get("universe")
    if explicit:
        tickers = [t.strip().upper() for t in explicit if t.strip()]
        logger.info(f"Universe: {len(tickers)} tickers from config override")
        return tickers

    # 2. Config-specified file path, falling back to repo-relative default
    file_path = cfg.get("tickers_file", DEFAULT_TICKERS_FILE)
    return _load_from_file(file_path)


def _load_from_file(path: str) -> List[str]:
    """Load tickers from a text file (one per line, # comments ignored)."""
    try:
        with open(path) as f:
            tickers = [
                line.strip().upper()
                for line in f
                if line.strip() and not line.strip().startswith("#")
            ]
        # Deduplicate while preserving order
        seen: set = set()
        unique = [t for t in tickers if not (t in seen or seen.add(t))]
        logger.info(f"Universe: loaded {len(unique)} tickers from {path}")
        return unique
    except FileNotFoundError:
        logger.warning(f"Ticker file not found: {path} — universe will be empty")
        return []
    except Exception as e:
        logger.warning(f"Failed to load ticker file {path}: {e}")
        return []
