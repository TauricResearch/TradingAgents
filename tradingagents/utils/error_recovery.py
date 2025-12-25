"""
Error Recovery Utilities.

This module provides utilities for saving partial analysis state when errors occur,
allowing users to resume or inspect work completed before the error.

Functions:
    save_partial_analysis: Save partial state to JSON file
    get_partial_analysis_filename: Generate filename for partial analysis
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def save_partial_analysis(state: Dict[str, Any], output_file: str) -> None:
    """
    Save partial analysis state to a JSON file.

    Handles non-serializable objects by converting them to strings.
    Creates parent directories if they don't exist.

    Args:
        state: Dictionary containing partial analysis state
        output_file: Path where to save the JSON file

    Raises:
        PermissionError: If unable to write to output_file location
        OSError: If unable to create parent directories

    Example:
        >>> state = {
        ...     "ticker": "AAPL",
        ...     "error": "Rate limit exceeded",
        ...     "analyst_reports": {"market": {...}}
        ... }
        >>> save_partial_analysis(state, "./results/partial_AAPL.json")
    """
    # Create parent directory if it doesn't exist
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert state to JSON-serializable format
    serializable_state = _make_serializable(state)

    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(serializable_state, f, indent=2, ensure_ascii=False)


def get_partial_analysis_filename(
    ticker: str,
    timestamp: Optional[datetime] = None,
    output_dir: Optional[str] = None,
) -> str:
    """
    Generate a filename for partial analysis output.

    Format: partial_analysis_{ticker}_{timestamp}.json

    Args:
        ticker: Stock ticker symbol
        timestamp: Timestamp for filename (default: now)
        output_dir: Output directory (default: TRADINGAGENTS_RESULTS_DIR or ./results)

    Returns:
        str: Full path to partial analysis file

    Example:
        >>> get_partial_analysis_filename("AAPL")
        './results/partial_analysis_AAPL_20241226_103045.json'
    """
    if timestamp is None:
        timestamp = datetime.now()

    if output_dir is None:
        output_dir = os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results")

    # Format: partial_analysis_{ticker}_{YYYYMMDD_HHMMSS}.json
    timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
    filename = f"partial_analysis_{ticker}_{timestamp_str}.json"

    return str(Path(output_dir) / filename)


def _make_serializable(obj: Any) -> Any:
    """
    Recursively convert objects to JSON-serializable format.

    Handles:
    - Dictionaries (recurse on values)
    - Lists/tuples (recurse on items)
    - datetime objects (convert to ISO format)
    - Other objects (convert to string)

    Args:
        obj: Object to make serializable

    Returns:
        JSON-serializable version of obj
    """
    if obj is None:
        return None

    if isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, dict):
        return {key: _make_serializable(value) for key, value in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [_make_serializable(item) for item in obj]

    if isinstance(obj, datetime):
        return obj.isoformat()

    # For everything else (including Mock objects), convert to string
    try:
        # Try to convert to dict if it has __dict__
        if hasattr(obj, '__dict__'):
            return {
                '_type': obj.__class__.__name__,
                '_str': str(obj),
            }
    except Exception:
        pass

    # Final fallback: convert to string
    return str(obj)
