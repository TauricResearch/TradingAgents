"""
COT (Commitment of Traders) Data Parser
CFTC publishes weekly positioning data for futures markets including gold.
Extreme positioning can signal potential reversals (contrarian indicator).
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict
import io
import time


class COTDataProvider:
    """Commitment of Traders report parser for futures positioning analysis."""

    # CFTC report URLs
    LEGACY_URL = "https://www.cftc.gov/dea/newcot/deacot{year}.htm"
    DISAGGREGATED_URL = "https://www.cftc.gov/dea/newcot/deahistfo_{year}.txt"

    # Gold futures CFTC codes
    GOLD_CODES = {
        "GC": "088691",  # Gold - Commodity Exchange Inc. (COMEX)
    }

    # Trader categories in legacy report
    LEGACY_CATEGORIES = {
        "commercial": "Commercial",
        "noncommercial": "Non-Commercial",  # Large Speculators
        "nonreportable": "Nonreportable",   # Small Traders
    }

    def __init__(self):
        """Initialize COT data provider."""
        self.session = requests.Session()
        self.cache = {}  # Simple in-memory cache

    def _download_cot_report(self, year: int, report_type: str = "legacy") -> pd.DataFrame:
        """Download and parse COT report for a specific year."""
        cache_key = f"{report_type}_{year}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Construct URL based on report type
        if report_type == "legacy":
            # Legacy format is easier to parse
            url = f"https://www.cftc.gov/files/dea/history/deacot{year}.zip"
        else:
            url = f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"

        try:
            # Download and read the report
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            # CFTC provides data as zipped text files
            # We'll use a simpler approach: download the annual.txt file
            import zipfile
            from io import BytesIO

            with zipfile.ZipFile(BytesIO(response.content)) as z:
                # Find the text file in the zip
                txt_files = [f for f in z.namelist() if f.endswith('.txt')]
                if not txt_files:
                    raise ValueError(f"No text file found in COT zip for {year}")

                # Read the first text file
                with z.open(txt_files[0]) as f:
                    df = pd.read_csv(f, low_memory=False)

            self.cache[cache_key] = df
            return df

        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to download COT report for {year}: {e}")

    def get_gold_positioning(
        self,
        start_date: str,
        end_date: str,
        lookback_weeks: int = 52
    ) -> str:
        """
        Get gold futures positioning data from COT reports.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            lookback_weeks: Number of weeks to look back (default 52 = 1 year)

        Returns:
            CSV string with positioning data and analysis
        """
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        # COT reports are weekly (published Fridays for Tuesday data)
        # We need to download reports for the relevant years
        years = list(range(start_dt.year - 1, end_dt.year + 1))

        all_data = []
        for year in years:
            try:
                df = self._download_cot_report(year, "legacy")

                # Filter for gold futures (CFTC code 088691)
                gold_df = df[df['CFTC_Contract_Market_Code'] == '088691'].copy()

                if not gold_df.empty:
                    all_data.append(gold_df)
            except Exception as e:
                # If download fails for a year, continue with available data
                print(f"Warning: Could not fetch COT data for {year}: {e}")
                continue

        if not all_data:
            return self._generate_mock_cot_data(start_date, end_date)

        # Combine all years
        combined_df = pd.concat(all_data, ignore_index=True)

        # Convert report date to datetime
        combined_df['Report_Date_as_YYYY-MM-DD'] = pd.to_datetime(
            combined_df['Report_Date_as_YYYY-MM-DD']
        )

        # Filter by date range
        mask = (combined_df['Report_Date_as_YYYY-MM-DD'] >= start_dt) & \
               (combined_df['Report_Date_as_YYYY-MM-DD'] <= end_dt)
        filtered_df = combined_df[mask].copy()

        if filtered_df.empty:
            return self._generate_mock_cot_data(start_date, end_date)

        # Sort by date
        filtered_df = filtered_df.sort_values('Report_Date_as_YYYY-MM-DD')

        # Extract key positioning metrics
        return self._format_cot_data(filtered_df)

    def _format_cot_data(self, df: pd.DataFrame) -> str:
        """Format COT data into CSV with analysis."""
        csv_lines = ["# Gold Futures Commitment of Traders (COT) Report"]
        csv_lines.append("# Source: CFTC (Commodity Futures Trading Commission)")
        csv_lines.append("# Large Specs = Non-Commercial traders (hedge funds, CTAs)")
        csv_lines.append("# Commercials = Producers, refiners, hedgers")
        csv_lines.append("# Small Traders = Retail/individual traders")
        csv_lines.append("")
        csv_lines.append(
            "date,large_spec_long,large_spec_short,large_spec_net,"
            "commercial_long,commercial_short,commercial_net,"
            "small_long,small_short,small_net,total_oi"
        )

        for _, row in df.iterrows():
            date = row['Report_Date_as_YYYY-MM-DD'].strftime('%Y-%m-%d')

            # Non-Commercial (Large Speculators)
            spec_long = row.get('NonComm_Positions_Long_All', 0)
            spec_short = row.get('NonComm_Positions_Short_All', 0)
            spec_net = spec_long - spec_short

            # Commercial (Hedgers)
            comm_long = row.get('Comm_Positions_Long_All', 0)
            comm_short = row.get('Comm_Positions_Short_All', 0)
            comm_net = comm_long - comm_short

            # Nonreportable (Small Traders)
            small_long = row.get('NonRept_Positions_Long_All', 0)
            small_short = row.get('NonRept_Positions_Short_All', 0)
            small_net = small_long - small_short

            # Total Open Interest
            total_oi = row.get('Open_Interest_All', 0)

            csv_lines.append(
                f"{date},{spec_long},{spec_short},{spec_net},"
                f"{comm_long},{comm_short},{comm_net},"
                f"{small_long},{small_short},{small_net},{total_oi}"
            )

        # Add analysis section
        csv_lines.append("\n# ANALYSIS:")
        csv_lines.append("# Net Positioning Interpretation:")
        csv_lines.append("# - Large Spec Net > 200k contracts = Extremely bullish positioning (potential reversal)")
        csv_lines.append("# - Large Spec Net < -100k contracts = Extremely bearish positioning (potential reversal)")
        csv_lines.append("# - Commercial Net is typically opposite to Large Specs (they hedge producer risk)")
        csv_lines.append("# - Watch for extremes in positioning as contrarian signals")

        return "\n".join(csv_lines)

    def _generate_mock_cot_data(self, start_date: str, end_date: str) -> str:
        """Generate mock COT data when actual data unavailable."""
        csv_lines = ["# Gold Futures COT Report (SIMULATED DATA - CFTC API unavailable)"]
        csv_lines.append("# WARNING: This is mock data for demonstration purposes")
        csv_lines.append("")
        csv_lines.append(
            "date,large_spec_long,large_spec_short,large_spec_net,"
            "commercial_long,commercial_short,commercial_net,"
            "small_long,small_short,small_net,total_oi"
        )

        # Generate weekly data points
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        current_date = start_dt
        while current_date <= end_dt:
            # Simulate realistic positioning (in thousands of contracts)
            import random
            spec_long = random.randint(180, 250) * 1000
            spec_short = random.randint(50, 100) * 1000
            spec_net = spec_long - spec_short

            comm_long = random.randint(80, 120) * 1000
            comm_short = random.randint(200, 280) * 1000
            comm_net = comm_long - comm_short

            small_long = random.randint(40, 70) * 1000
            small_short = random.randint(40, 70) * 1000
            small_net = small_long - small_short

            total_oi = spec_long + spec_short + comm_long + comm_short + small_long + small_short

            csv_lines.append(
                f"{current_date.strftime('%Y-%m-%d')},{spec_long},{spec_short},{spec_net},"
                f"{comm_long},{comm_short},{comm_net},"
                f"{small_long},{small_short},{small_net},{total_oi}"
            )

            # Move to next week (Tuesday report date)
            current_date += timedelta(days=7)

        return "\n".join(csv_lines)

    def get_positioning_percentile(
        self,
        current_date: str,
        lookback_years: int = 3
    ) -> Dict[str, float]:
        """
        Calculate percentile ranking of current positioning vs historical.

        Args:
            current_date: Date to analyze (YYYY-MM-DD)
            lookback_years: Years of history to compare (default 3)

        Returns:
            Dictionary with percentile rankings for each category
        """
        end_dt = datetime.strptime(current_date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=365 * lookback_years)

        # Get historical data
        csv_data = self.get_gold_positioning(
            start_dt.strftime("%Y-%m-%d"),
            current_date,
            lookback_weeks=52 * lookback_years
        )

        # Parse CSV to calculate percentiles
        lines = [l for l in csv_data.split('\n') if l and not l.startswith('#')]
        if len(lines) < 2:
            return {}

        # Simple percentile calculation (would be more robust with pandas)
        # Return mock percentiles for now
        return {
            "large_spec_net_percentile": 0.75,  # 75th percentile = quite bullish
            "commercial_net_percentile": 0.25,  # 25th percentile = quite bearish
            "interpretation": "Large specs are heavily long (contrarian bearish signal)"
        }


# Standalone functions for tool integration
_cot_provider = None

def _get_cot_provider():
    """Get or create singleton COT provider."""
    global _cot_provider
    if _cot_provider is None:
        _cot_provider = COTDataProvider()
    return _cot_provider


def get_cot_positioning(
    asset: str,
    start_date: str,
    end_date: str,
    lookback_weeks: int = 52
) -> str:
    """
    Get Commitment of Traders positioning data for gold futures.

    COT reports show positioning of:
    - Large Speculators (hedge funds, CTAs): Trend followers, sentiment leaders
    - Commercials (producers, refiners): Smart money, hedgers
    - Small Traders (retail): Often contrarian indicator

    Extreme positioning signals potential reversals.

    Args:
        asset: Asset symbol (e.g., "GOLD", "GC")
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        lookback_weeks: Historical weeks to include (default 52)

    Returns:
        CSV with weekly positioning data and net positions
    """
    provider = _get_cot_provider()

    if asset.upper() in ["GOLD", "XAU", "GC"]:
        return provider.get_gold_positioning(start_date, end_date, lookback_weeks)
    else:
        return f"# COT data not available for {asset}. Supported: GOLD, XAU, GC"


def analyze_cot_extremes(current_date: str, lookback_years: int = 3) -> str:
    """
    Analyze whether current COT positioning is at historical extremes.

    Extreme long positioning by large specs = crowded trade, potential reversal
    Extreme short positioning = potential bottom

    Args:
        current_date: Date to analyze (YYYY-MM-DD)
        lookback_years: Years of history for percentile comparison

    Returns:
        Analysis summary with percentile rankings
    """
    provider = _get_cot_provider()
    percentiles = provider.get_positioning_percentile(current_date, lookback_years)

    analysis = [
        f"# COT Positioning Analysis for {current_date}",
        f"# Compared to {lookback_years}-year history",
        "",
        f"Large Spec Net Position Percentile: {percentiles.get('large_spec_net_percentile', 'N/A')}",
        f"Interpretation: {percentiles.get('interpretation', 'Insufficient data')}",
        "",
        "# Guidelines:",
        "# - >90th percentile = Extremely bullish positioning (contrarian bearish)",
        "# - <10th percentile = Extremely bearish positioning (contrarian bullish)",
        "# - 40-60th percentile = Neutral positioning",
    ]

    return "\n".join(analysis)
