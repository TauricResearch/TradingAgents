"""Strategy Effectiveness Scorecard — compare previous signals vs actual price movement.

After each fortnightly run, loads the previous run's strategy signals and compares
their directional calls against actual price movement to track which strategies
are most predictive for the portfolio over time.
"""

from __future__ import annotations

import json
from pathlib import Path

import yfinance as yf


def _load_previous_signals(ticker: str, current_date: str, analyses_dir: Path) -> tuple[list[dict], str]:
    """Find the most recent signals.json for ticker before current_date.

    Returns (signals_list, prev_date) or ([], "").
    """
    best_date = ""
    best_signals: list[dict] = []

    if not analyses_dir.exists():
        return [], ""

    for d in analyses_dir.iterdir():
        if not d.is_dir() or not d.name.startswith(f"{ticker}_"):
            continue
        sf = d / "signals.json"
        if not sf.exists():
            continue
        # Extract date from dirname: TICKER_YYYY-MM-DD
        parts = d.name.split("_", 1)
        if len(parts) < 2:
            continue
        d_date = parts[1]
        if d_date >= current_date:
            continue
        if d_date > best_date:
            try:
                best_signals = json.loads(sf.read_text())
                best_date = d_date
            except Exception:
                continue

    return best_signals, best_date


def _get_price_change(ticker: str, from_date: str, to_date: str) -> float | None:
    """Get percentage price change between two dates. Returns None on failure."""
    try:
        hist = yf.Ticker(ticker).history(start=from_date, end=to_date)
        if hist.empty or len(hist) < 2:
            return None
        return ((hist["Close"].iloc[-1] / hist["Close"].iloc[0]) - 1) * 100
    except Exception:
        return None


def _score_signal(signal: dict, pct_change: float) -> dict:
    """Score a single signal against actual price movement.

    Returns dict with: name, direction, signal, pct_change, correct (bool), detail.
    """
    direction = signal.get("direction", "NEUTRAL")
    name = signal.get("name", "")
    value_label = signal.get("value_label", "")

    # SUPPORTS = bullish call, CONTRADICTS = bearish call
    if direction == "SUPPORTS":
        predicted_up = True
    elif direction == "CONTRADICTS":
        predicted_up = False
    else:
        # NEUTRAL — not a directional call, skip scoring
        return {
            "name": name,
            "direction": direction,
            "value_label": value_label,
            "pct_change": round(pct_change, 2),
            "correct": None,  # not scored
        }

    actual_up = pct_change > 0
    correct = predicted_up == actual_up

    return {
        "name": name,
        "direction": direction,
        "value_label": value_label,
        "pct_change": round(pct_change, 2),
        "correct": correct,
    }


def compute_scorecard(
    tickers: set[str],
    current_date: str,
    analyses_dir: Path,
) -> list[dict]:
    """Compare previous strategy signals vs actual price movement for all tickers.

    Returns list of scored signal dicts with keys:
        ticker, name, direction, value_label, pct_change, correct, prev_date
    """
    results: list[dict] = []

    for ticker in sorted(tickers):
        prev_signals, prev_date = _load_previous_signals(ticker, current_date, analyses_dir)
        if not prev_signals or not prev_date:
            continue

        pct_change = _get_price_change(ticker, prev_date, current_date)
        if pct_change is None:
            continue

        for sig in prev_signals:
            scored = _score_signal(sig, pct_change)
            scored["ticker"] = ticker
            scored["prev_date"] = prev_date
            results.append(scored)

    return results


def scorecard_summary(scored: list[dict]) -> dict:
    """Aggregate scorecard results into per-strategy accuracy stats.

    Returns {strategy_name: {correct: int, incorrect: int, total: int, accuracy: float}}.
    """
    from collections import defaultdict
    stats: dict[str, dict] = defaultdict(lambda: {"correct": 0, "incorrect": 0, "total": 0})

    for s in scored:
        if s.get("correct") is None:
            continue  # skip NEUTRAL
        name = s["name"]
        stats[name]["total"] += 1
        if s["correct"]:
            stats[name]["correct"] += 1
        else:
            stats[name]["incorrect"] += 1

    for name in stats:
        t = stats[name]["total"]
        stats[name]["accuracy"] = stats[name]["correct"] / t if t > 0 else 0.0

    return dict(stats)


def persist_scorecard(scored: list[dict], date: str, data_dir: Path) -> Path:
    """Merge current scorecard results into cumulative data/strategy_scorecard.json.

    File structure:
    {
      "runs": [{"date": "2026-04-14", "scored": 12, "correct": 8}],
      "strategies": {
        "momentum": {"correct": 5, "incorrect": 2, "total": 7, "accuracy": 0.714},
        ...
      },
      "updated": "2026-04-16"
    }

    Returns path to the scorecard file.
    """
    path = data_dir / "strategy_scorecard.json"

    # Load existing
    cumulative: dict = {"runs": [], "strategies": {}, "updated": ""}
    if path.exists():
        try:
            cumulative = json.loads(path.read_text())
        except Exception:
            pass

    # Skip if this date already recorded
    existing_dates = {r["date"] for r in cumulative.get("runs", [])}
    if date in existing_dates:
        return path

    # Merge current run's per-strategy stats
    current = scorecard_summary(scored)
    strategies = cumulative.get("strategies", {})
    for name, stats in current.items():
        if name in strategies:
            strategies[name]["correct"] += stats["correct"]
            strategies[name]["incorrect"] += stats["incorrect"]
            strategies[name]["total"] += stats["total"]
        else:
            strategies[name] = {
                "correct": stats["correct"],
                "incorrect": stats["incorrect"],
                "total": stats["total"],
            }
        t = strategies[name]["total"]
        strategies[name]["accuracy"] = round(strategies[name]["correct"] / t, 4) if t else 0.0

    # Append run summary
    directional = [s for s in scored if s.get("correct") is not None]
    cumulative["runs"].append({
        "date": date,
        "scored": len(directional),
        "correct": sum(1 for s in directional if s["correct"]),
    })
    cumulative["strategies"] = strategies
    cumulative["updated"] = date

    data_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cumulative, indent=2))
    return path
