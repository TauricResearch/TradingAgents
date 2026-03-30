"""Finviz vendor implementations for scanner data methods."""

import logging

logger = logging.getLogger(__name__)

_GAP_FILTERS = {
    "Market Cap.": "+Mid (over $2bln)",
    "Net Profit Margin": "Positive (>0%)",
    "Average Volume": "Over 2M",
    "Price": "Over $5",
    "Gap": "Up 5%",
}


def get_gap_candidates_finviz() -> str:
    """Fetch gap-up candidates using Finviz native gap filter (exact, not approximated).

    Returns a formatted Markdown table of gap candidates filtered by the
    gatekeeper criteria plus a native Gap Up 5% screener.

    Raises:
        ConnectionError: if finvizfinance is not installed or the screener call fails.
    """
    try:
        from finvizfinance.screener.overview import Overview  # optional dependency

        foverview = Overview()
        foverview.set_filter(filters_dict=_GAP_FILTERS)
        df = foverview.screener_view()

        if df is None or df.empty:
            return "No stocks matched the gatekeeper gap criteria today."

        if "Volume" in df.columns:
            df = df.sort_values(by="Volume", ascending=False)

        cols = [c for c in ["Ticker", "Sector", "Price", "Volume"] if c in df.columns]
        rows = df.head(5)[cols].to_dict("records")

        lines = ["# Gap Candidates (Finviz)\n"]
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "|".join(["---"] * len(cols)) + "|")
        for row in rows:
            lines.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
        return "\n".join(lines) + "\n"

    except ImportError:
        raise ConnectionError(
            "finvizfinance is not installed — cannot use Finviz gap filter. "
            "Install it with: pip install finvizfinance"
        )
    except Exception as e:
        raise ConnectionError(f"Finviz gap screener failed: {e}") from e
