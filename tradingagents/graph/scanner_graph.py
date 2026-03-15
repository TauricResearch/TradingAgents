# tradingagents/graph/scanner_graph.py

import datetime
from typing import Any, Dict, Optional

from tradingagents.dataflows.config import set_config
from tradingagents.default_config import DEFAULT_CONFIG

from .scanner_setup import ScannerGraphSetup


class MacroScannerGraph:
    """Orchestrates the Global Macro Scanner workflow.

    The scanner runs three parallel data-collection phases followed by a
    synthesis phase:

    Phase 1 (parallel):
        - Geopolitical / macro news scanner
        - Market movers + index performance scanner
        - Sector performance scanner

    Phase 2 (sequential):
        - Industry deep dive (technology sector by default)

    Phase 3 (sequential):
        - Macro synthesis — combines all outputs into a single summary
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialise the scanner graph.

        Args:
            config: Optional configuration dictionary.  Defaults to
                ``DEFAULT_CONFIG`` when not provided.
        """
        self.config = config or DEFAULT_CONFIG
        set_config(self.config)

        self.graph_setup = ScannerGraphSetup()
        self.graph = self.graph_setup.setup_graph()

    def scan(self, scan_date: Optional[str] = None) -> Dict[str, Any]:
        """Execute the macro scan and return the final state.

        Args:
            scan_date: Date string in ``YYYY-MM-DD`` format.  Defaults to
                today's date when not provided.

        Returns:
            Final LangGraph state dictionary containing all scan reports and
            the ``macro_scan_summary`` field.
        """
        if scan_date is None:
            scan_date = datetime.date.today().isoformat()

        initial_state = {
            "messages": [],
            "scan_date": scan_date,
            "geopolitical_report": "",
            "market_movers_report": "",
            "sector_performance_report": "",
            "industry_deep_dive_report": "",
            "macro_scan_summary": "",
            "sender": "",
        }

        final_state = self.graph.invoke(
            initial_state,
            {"recursion_limit": self.config.get("max_recur_limit", 100)},
        )

        return final_state
