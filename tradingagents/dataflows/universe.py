"""Ticker universe — single source of truth.

All scanners that need a list of tickers should call load_universe(config).
Do NOT hardcode "data/tickers.txt" in scanner files — import this module instead.

Priority order:
  1. config["discovery"]["universe"]        — explicit list (tests / overrides)
  2. config["discovery"]["universe_source"] — dynamic index ("russell1000")
  3. config["tickers_file"]                 — path from top-level config
  4. Default: data/tickers.txt resolved relative to repo root
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)

# Resolved once at import time — works regardless of cwd
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_TICKERS_FILE = str(_REPO_ROOT / "data" / "tickers.txt")
_UNIVERSE_CACHE_FILE = _REPO_ROOT / "data" / "universe_cache.json"
_CACHE_TTL_SECONDS = 7 * 24 * 3600  # refresh weekly


def load_universe(config: Optional[Dict[str, Any]] = None) -> List[str]:
    """Return the full ticker universe as a list of uppercase strings.

    Args:
        config: Top-level app config dict. If None, falls back to default file.

    Returns:
        Deduplicated list of ticker symbols in the order they appear in the source.
    """
    cfg = config or {}

    # 1. Explicit list in config (useful for tests or targeted overrides)
    explicit = cfg.get("discovery", {}).get("universe")
    if explicit:
        tickers = [t.strip().upper() for t in explicit if t.strip()]
        logger.info(f"Universe: {len(tickers)} tickers from config override")
        return tickers

    # 2. Dynamic index source
    source = cfg.get("discovery", {}).get("universe_source", "")
    if source == "russell1000":
        tickers = _load_russell1000()
        if tickers:
            return tickers
        logger.warning("Russell 1000 fetch failed — falling back to tickers.txt")

    # 3. Config-specified file path, falling back to repo-relative default
    file_path = cfg.get("tickers_file", DEFAULT_TICKERS_FILE)
    return _load_from_file(file_path)


def _load_russell1000() -> List[str]:
    """Fetch Russell 1000 constituents from iShares IWB ETF holdings, with weekly disk cache."""
    # Return cached copy if fresh
    cached = _read_universe_cache("russell1000")
    if cached:
        return cached

    logger.info("Fetching Russell 1000 constituents from iShares IWB holdings...")
    try:
        import io
        import urllib.request

        import pandas as pd

        url = (
            "https://www.ishares.com/us/products/239707/ISHARES-RUSSELL-1000-ETF"
            "/1467271812596.ajax?fileType=csv&fileName=IWB_holdings&dataType=fund"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            content = r.read().decode("utf-8", errors="ignore")

        # iShares CSV has a few header rows before the actual data
        df = pd.read_csv(io.StringIO(content), skiprows=9)

        if "Ticker" not in df.columns:
            logger.warning("Could not find Ticker column in iShares IWB CSV")
            return []

        # Only take equity rows — excludes cash collateral, money market, etc.
        if "Asset Class" in df.columns:
            df = df[df["Asset Class"].astype(str).str.strip() == "Equity"]

        # iShares uses compact tickers for some dual-class shares (no hyphen).
        # Map the compact form → canonical yfinance symbol.
        _ISHARES_REMAP = {
            "BRKB": "BRK-B",
            "BFA": "BF-A",
            "BFB": "BF-B",
            "HEIA": "HEI-A",
            "LENB": "LEN-B",
            "UHALB": "UHAL-B",
            "CWENA": "CWEN-A",
            "FWONA": "FWON-A",
            "LBTYA": "LBTY-A",
            "LBTYK": "LBTY-K",
            "LLYVA": "LLYV-A",
            "LBRDA": "LBRD-A",
            "LBRDK": "LBRD-K",
            "GLIBA": "GLIB-A",
            "NWSA": "NWS-A",
            "FOXA": "FOX-A",
        }

        tickers = []
        for t in df["Ticker"].dropna():
            s = str(t).strip().upper().replace(".", "-")
            # Valid tickers: 1-6 alpha chars only
            if not (s and len(s) <= 7 and s.replace("-", "").isalpha()):
                continue
            s = _ISHARES_REMAP.get(s, s)
            tickers.append(s)

        # Deduplicate while preserving order (by weight — iShares sorts by weight desc)
        seen: set = set()
        tickers = [t for t in tickers if not (t in seen or seen.add(t))]

        if not tickers:
            logger.warning("No tickers parsed from iShares IWB CSV")
            return []

        _write_universe_cache("russell1000", tickers)
        logger.info(f"Universe: {len(tickers)} Russell 1000 tickers (cached)")
        return tickers

    except Exception as e:
        logger.warning(f"Failed to fetch Russell 1000 from iShares: {e}")
        return []


def _read_universe_cache(key: str) -> List[str]:
    """Return cached ticker list if it exists and is within TTL."""
    try:
        if not _UNIVERSE_CACHE_FILE.exists():
            return []
        data = json.loads(_UNIVERSE_CACHE_FILE.read_text())
        entry = data.get(key, {})
        if time.time() - entry.get("ts", 0) < _CACHE_TTL_SECONDS:
            tickers = entry.get("tickers", [])
            logger.info(f"Universe: {len(tickers)} {key} tickers (from disk cache)")
            return tickers
    except Exception:
        pass
    return []


def _write_universe_cache(key: str, tickers: List[str]) -> None:
    """Persist ticker list to disk cache."""
    try:
        data: dict = {}
        if _UNIVERSE_CACHE_FILE.exists():
            data = json.loads(_UNIVERSE_CACHE_FILE.read_text())
        data[key] = {"ts": time.time(), "tickers": tickers}
        _UNIVERSE_CACHE_FILE.write_text(json.dumps(data))
    except Exception as e:
        logger.debug(f"Failed to write universe cache: {e}")


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
