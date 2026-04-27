"""Scanner conditional logic for determining continuation in scanner graph."""

from tradingagents.agents.utils.scanner_states import ScannerState

_ERROR_PREFIXES = (
    "Error",
    "No data",
    "No quotes",
    "No movers",
    "No news",
    "No industry",
    "Invalid",
)


def _report_is_valid(report: str) -> bool:
    """Return True when *report* contains usable data (non-empty, non-error)."""
    if not report or not report.strip():
        return False
    return not any(report.startswith(prefix) for prefix in _ERROR_PREFIXES)


class ScannerConditionalLogic:
    """Conditional logic for scanner graph flow control."""

    def _check_report(self, state: ScannerState, field: str) -> bool:
        return _report_is_valid(state.get(field, ""))

    def should_continue_geopolitical(self, state: ScannerState) -> bool:
        """
        Determine if geopolitical scanning should continue.

        Returns True only when the geopolitical report contains usable data.
        """
        return self._check_report(state, "geopolitical_report")

    def should_continue_movers(self, state: ScannerState) -> bool:
        """
        Determine if market movers scanning should continue.

        Returns True only when the market movers report contains usable data.
        """
        return self._check_report(state, "market_movers_report")

    def should_continue_sector(self, state: ScannerState) -> bool:
        """
        Determine if sector scanning should continue.

        Returns True only when the sector performance report contains usable data.
        """
        return self._check_report(state, "sector_performance_report")

    def should_continue_industry(self, state: ScannerState) -> bool:
        """
        Determine if industry deep dive should continue.

        Returns True only when the industry deep dive report contains usable data.
        """
        return self._check_report(state, "industry_deep_dive_report")
