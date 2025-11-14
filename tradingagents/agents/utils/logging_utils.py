from __future__ import annotations

def log_report_preview(agent_name: str, ticker: str, report: str, *, max_chars: int = 800) -> None:
    """Log the agent's report in full so the operator can read the entire analysis."""
    if not report:
        try:
            print(f"[{agent_name}] No direct narrative output returned for {ticker} (tool-only response).")
        except Exception:
            pass
        return

    try:
        print(f"[{agent_name}] Report for {ticker}:\n{report.strip()}\n")
    except Exception:
        pass
