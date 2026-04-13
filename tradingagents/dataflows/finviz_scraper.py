"""
Finviz + Yahoo Finance Hybrid - Short Interest Discovery
Uses Finviz to discover tickers with high short interest, then Yahoo Finance for exact data
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Annotated

import requests
from bs4 import BeautifulSoup

from tradingagents.dataflows.y_finance import get_ticker_info
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)


def get_short_interest(
    min_short_interest_pct: Annotated[float, "Minimum short interest % of float"] = 10.0,
    min_days_to_cover: Annotated[float, "Minimum days to cover ratio"] = 2.0,
    top_n: Annotated[int, "Number of top results to return"] = 20,
    return_structured: Annotated[bool, "Return dict with raw data instead of markdown"] = False,
):
    """
    Discover stocks with high short interest using Finviz + Yahoo Finance.

    Strategy: Finviz filters stocks by short interest (discovery),
    then Yahoo Finance provides exact short % data.

    This is a TRUE DISCOVERY tool - finds stocks we may not know about,
    not checking a predefined watchlist.

    Args:
        min_short_interest_pct: Minimum short interest as % of float
        min_days_to_cover: Minimum days to cover ratio
        top_n: Number of top results to return
        return_structured: If True, returns list of dicts instead of markdown

    Returns:
        If return_structured=True: list of candidate dicts with ticker, short_interest_pct, signal, etc.
        If return_structured=False: Formatted markdown report
    """
    try:
        # Step 1: Use Finviz screener to DISCOVER tickers with high short interest
        logger.info(
            f"Discovering tickers with short interest >{min_short_interest_pct}% from Finviz..."
        )

        # Determine Finviz filter
        if min_short_interest_pct >= 20:
            short_filter = "sh_short_o20"
        elif min_short_interest_pct >= 15:
            short_filter = "sh_short_o15"
        elif min_short_interest_pct >= 10:
            short_filter = "sh_short_o10"
        else:
            short_filter = "sh_short_o5"

        # Build Finviz URL (v=152 is simple view)
        base_url = f"https://finviz.com/screener.ashx?v=152&f={short_filter}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        }

        discovered_tickers = []

        # Scrape first 3 pages (60 stocks)
        for page_num in range(1, 4):
            if page_num == 1:
                url = base_url
            else:
                offset = (page_num - 1) * 20 + 1
                url = f"{base_url}&r={offset}"

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Find ticker links in the page
            ticker_links = soup.find_all("a", href=re.compile(r"quote\.ashx\?t="))

            for link in ticker_links:
                ticker = link.get_text(strip=True)
                # Validate it's a ticker (1-5 uppercase letters)
                if re.match(r"^[A-Z]{1,5}$", ticker) and ticker not in discovered_tickers:
                    discovered_tickers.append(ticker)

        if not discovered_tickers:
            if return_structured:
                return []
            return f"No stocks discovered with short interest >{min_short_interest_pct}% on Finviz."

        logger.info(f"Discovered {len(discovered_tickers)} tickers from Finviz")
        logger.info("Fetching detailed short interest data from Yahoo Finance...")

        # Step 2: Use Yahoo Finance to get EXACT short interest data for discovered tickers
        def fetch_short_data(ticker):
            try:
                info = get_ticker_info(ticker)

                # Get short interest data
                short_pct = info.get("shortPercentOfFloat", info.get("sharesPercentSharesOut", 0))
                if short_pct and isinstance(short_pct, (int, float)):
                    short_pct = short_pct * 100  # Convert to percentage
                else:
                    return None

                # Verify it meets criteria (Finviz filter might be outdated)
                if short_pct >= min_short_interest_pct:
                    price = info.get("currentPrice", info.get("regularMarketPrice", 0))
                    market_cap = info.get("marketCap", 0)
                    volume = info.get("volume", info.get("regularMarketVolume", 0))

                    # Days to cover (short ratio): shares short / avg daily volume
                    days_to_cover = info.get("shortRatio")
                    if days_to_cover is None or not isinstance(days_to_cover, (int, float)):
                        days_to_cover = 0.0

                    # Apply days-to-cover filter
                    if days_to_cover < min_days_to_cover:
                        return None

                    # Categorize squeeze potential
                    if short_pct >= 30:
                        signal = "extreme_squeeze_risk"
                    elif short_pct >= 20:
                        signal = "high_squeeze_potential"
                    elif short_pct >= 15:
                        signal = "moderate_squeeze_potential"
                    else:
                        signal = "low_squeeze_potential"

                    return {
                        "ticker": ticker,
                        "price": price,
                        "market_cap": market_cap,
                        "volume": volume,
                        "short_interest_pct": short_pct,
                        "days_to_cover": days_to_cover,
                        "signal": signal,
                    }
            except Exception:
                return None

        # Fetch data in parallel (faster)
        all_candidates = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(fetch_short_data, ticker): ticker for ticker in discovered_tickers
            }

            for future in as_completed(futures):
                result = future.result()
                if result:
                    all_candidates.append(result)

        if not all_candidates:
            if return_structured:
                return []
            return f"No stocks with verified short interest >{min_short_interest_pct}% (Finviz found {len(discovered_tickers)} tickers but Yahoo Finance data didn't confirm)."

        # Sort by short interest percentage (highest first)
        sorted_candidates = sorted(
            all_candidates, key=lambda x: x["short_interest_pct"], reverse=True
        )[:top_n]

        # Return structured data if requested
        if return_structured:
            return sorted_candidates

        # Format output
        report = "# Discovered High Short Interest Stocks\n\n"
        report += f"**Criteria**: Short Interest >{min_short_interest_pct}%\n"
        report += "**Data Source**: Finviz Screener (Web Scraping)\n"
        report += f"**Total Discovered**: {len(all_candidates)} stocks\n\n"
        report += f"**Top {len(sorted_candidates)} Candidates**:\n\n"
        report += "| Ticker | Price | Market Cap | Volume | Short % | Signal |\n"
        report += "|--------|-------|------------|--------|---------|--------|\n"

        for candidate in sorted_candidates:
            market_cap_str = format_market_cap(candidate["market_cap"])
            report += f"| {candidate['ticker']} | "
            report += f"${candidate['price']:.2f} | "
            report += f"{market_cap_str} | "
            report += f"{candidate['volume']:,} | "
            report += f"{candidate['short_interest_pct']:.1f}% | "
            report += f"{candidate['signal']} |\n"

        report += "\n\n## Signal Definitions\n\n"
        report += "- **extreme_squeeze_risk**: Short interest >30% - Very high squeeze potential\n"
        report += "- **high_squeeze_potential**: Short interest 20-30% - High squeeze risk\n"
        report += (
            "- **moderate_squeeze_potential**: Short interest 15-20% - Moderate squeeze risk\n"
        )
        report += "- **low_squeeze_potential**: Short interest 10-15% - Lower squeeze risk\n\n"
        report += "**Note**: High short interest alone doesn't guarantee a squeeze. Look for positive catalysts.\n"

        return report

    except requests.exceptions.RequestException as e:
        if return_structured:
            return []
        return f"Error scraping Finviz: {str(e)}"
    except Exception as e:
        if return_structured:
            return []
        return f"Unexpected error discovering short interest stocks: {str(e)}"


def parse_market_cap(market_cap_text: str) -> float:
    """Parse market cap from Finviz format (e.g., '1.23B', '456M')."""
    if not market_cap_text or market_cap_text == "-":
        return 0.0

    market_cap_text = market_cap_text.upper().strip()

    # Extract number and multiplier
    match = re.match(r"([0-9.]+)([BMK])?", market_cap_text)
    if not match:
        return 0.0

    number = float(match.group(1))
    multiplier = match.group(2)

    if multiplier == "B":
        return number * 1_000_000_000
    elif multiplier == "M":
        return number * 1_000_000
    elif multiplier == "K":
        return number * 1_000
    else:
        return number


def format_market_cap(market_cap: float) -> str:
    """Format market cap for display."""
    if market_cap >= 1_000_000_000:
        return f"${market_cap / 1_000_000_000:.2f}B"
    elif market_cap >= 1_000_000:
        return f"${market_cap / 1_000_000:.2f}M"
    else:
        return f"${market_cap:,.0f}"


def get_finviz_short_interest(
    min_short_interest_pct: float = 10.0,
    min_days_to_cover: float = 2.0,
    top_n: int = 20,
) -> str:
    """Alias for get_short_interest to match registry naming convention"""
    return get_short_interest(min_short_interest_pct, min_days_to_cover, top_n)


def get_insider_buying_screener(
    transaction_type: Annotated[str, "Transaction type: 'buy', 'sell', or 'any'"] = "buy",
    lookback_days: Annotated[int, "Days to look back for transactions"] = 7,
    min_value: Annotated[int, "Minimum transaction value in dollars"] = 25000,
    top_n: Annotated[int, "Number of top results to return"] = 20,
    return_structured: Annotated[bool, "Return list of dicts instead of markdown"] = False,
    deduplicate: Annotated[bool, "If False, return all transactions without deduplication"] = True,
):
    """
    Discover stocks with recent insider buying/selling using OpenInsider.

    LEADING INDICATOR: Insiders buying their own stock before price moves.
    Results are sorted by transaction value (largest first).

    Args:
        transaction_type: "buy" for purchases, "sell" for sales
        lookback_days: Days to look back (default 7)
        min_value: Minimum transaction value in dollars
        top_n: Number of top results to return
        return_structured: If True, returns list of dicts instead of markdown

    Returns:
        If return_structured=True: list of transaction dicts
        If return_structured=False: Formatted markdown report
    """
    try:
        filter_desc = "insider buying" if transaction_type == "buy" else "insider selling"
        logger.info(f"Discovering tickers with {filter_desc} from OpenInsider...")

        # OpenInsider screener URL
        # xp=1 means exclude private transactions
        # fd=7 means last 7 days filing date
        # vl=25 means minimum value $25k
        if transaction_type == "buy":
            url = f"http://openinsider.com/screener?s=&o=&pl=&ph=&ll=&lh=&fd={lookback_days}&fdr=&td=0&tdr=&fdlyl=&fdlyh=&dtefrom=&dteto=&xp=1&vl={min_value // 1000}&vh=&ocl=&och=&session=all&cnt=100&page=1"
        else:
            url = f"http://openinsider.com/screener?s=&o=&pl=&ph=&ll=&lh=&fd={lookback_days}&fdr=&td=0&tdr=&fdlyl=&fdlyh=&dtefrom=&dteto=&xs=1&vl={min_value // 1000}&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=4&cnt=100&page=1"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        }

        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Find the main data table
        table = soup.find("table", class_="tinytable")
        if not table:
            return f"No {filter_desc} data found on OpenInsider."

        tbody = table.find("tbody")
        if not tbody:
            return f"No {filter_desc} data found on OpenInsider."

        rows = tbody.find_all("tr")

        transactions = []

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 12:
                continue

            try:
                # OpenInsider columns:
                # 0: X (checkbox), 1: Filing Date, 2: Trade Date, 3: Ticker, 4: Company Name
                # 5: Insider Name, 6: Title, 7: Trade Type, 8: Price, 9: Qty, 10: Owned, 11: ΔOwn, 12: Value

                ticker_cell = cells[3]
                ticker_link = ticker_cell.find("a")
                ticker = ticker_link.get_text(strip=True) if ticker_link else ""

                if not ticker or not re.match(r"^[A-Z]{1,5}$", ticker):
                    continue

                company = cells[4].get_text(strip=True)[:40] if len(cells) > 4 else ""
                insider_name = cells[5].get_text(strip=True)[:25] if len(cells) > 5 else ""
                title_raw = cells[6].get_text(strip=True) if len(cells) > 6 else ""
                # "10%" means 10% beneficial owner - clarify for readability
                title = "10% Owner" if title_raw == "10%" else title_raw[:20]
                trade_type = cells[7].get_text(strip=True) if len(cells) > 7 else ""
                price = cells[8].get_text(strip=True) if len(cells) > 8 else ""
                qty = cells[9].get_text(strip=True) if len(cells) > 9 else ""
                value_str = cells[12].get_text(strip=True) if len(cells) > 12 else ""

                # Filter by transaction type
                trade_type_lower = trade_type.lower()
                if (
                    transaction_type == "buy"
                    and "buy" not in trade_type_lower
                    and "p -" not in trade_type_lower
                ):
                    continue
                if (
                    transaction_type == "sell"
                    and "sale" not in trade_type_lower
                    and "s -" not in trade_type_lower
                ):
                    continue

                # Parse value for sorting
                value_num = 0
                if value_str:
                    # Remove $ and + signs, handle K/M suffixes
                    clean_value = (
                        value_str.replace("$", "").replace("+", "").replace(",", "").strip()
                    )
                    try:
                        if "M" in clean_value:
                            value_num = float(clean_value.replace("M", "")) * 1_000_000
                        elif "K" in clean_value:
                            value_num = float(clean_value.replace("K", "")) * 1_000
                        else:
                            value_num = float(clean_value)
                    except ValueError:
                        value_num = 0

                transactions.append(
                    {
                        "ticker": ticker,
                        "company": company,
                        "insider": insider_name,
                        "title": title,
                        "trade_type": trade_type,
                        "price": price,
                        "qty": qty,
                        "value_str": value_str,
                        "value_num": value_num,
                    }
                )

            except Exception:
                continue

        if not transactions:
            if return_structured:
                return []
            return f"No {filter_desc} transactions found in the last {lookback_days} days."

        # Sort by value (largest first)
        transactions.sort(key=lambda x: x["value_num"], reverse=True)

        # Return all transactions without deduplication if requested
        if return_structured and not deduplicate:
            logger.info(f"Returning all {len(transactions)} {filter_desc} transactions (no dedup)")
            return transactions

        # Deduplicate by ticker, keeping the largest transaction per ticker
        seen_tickers = set()
        unique_transactions = []
        for t in transactions:
            if t["ticker"] not in seen_tickers:
                seen_tickers.add(t["ticker"])
                unique_transactions.append(t)
            if len(unique_transactions) >= top_n:
                break

        logger.info(
            f"Discovered {len(unique_transactions)} tickers with {filter_desc} (sorted by value)"
        )

        # Return structured data if requested
        if return_structured:
            return unique_transactions

        # Format report
        report_lines = [
            f"# Insider {'Buying' if transaction_type == 'buy' else 'Selling'} Report",
            f"*Top {len(unique_transactions)} stocks by transaction value (last {lookback_days} days)*\n",
            "| Ticker | Company | Insider | Title | Value | Price |",
            "|--------|---------|---------|-------|-------|-------|",
        ]

        for t in unique_transactions:
            report_lines.append(
                f"| {t['ticker']} | {t['company']} | {t['insider']} | {t['title']} | {t['value_str']} | {t['price']} |"
            )

        report_lines.append(
            f"\n**Total: {len(unique_transactions)} stocks with significant {filter_desc}**"
        )
        report_lines.append("*Sorted by transaction value (largest first)*")

        return "\n".join(report_lines)

    except requests.exceptions.RequestException as e:
        if return_structured:
            return []
        return f"Error fetching insider data from OpenInsider: {e}"
    except Exception as e:
        if return_structured:
            return []
        return f"Error processing insider screener: {e}"


def get_finviz_insider_buying(
    transaction_type: str = "buy",
    lookback_days: int = 7,
    min_value: int = 25000,
    top_n: int = 20,
    return_structured: bool = False,
    deduplicate: bool = True,
):
    """Alias for get_insider_buying_screener to match registry naming convention.

    Args:
        transaction_type: "buy" for purchases, "sell" for sales
        lookback_days: Days to look back (default 7)
        min_value: Minimum transaction value in dollars
        top_n: Number of top results to return
        return_structured: If True, returns list of dicts instead of markdown
        deduplicate: If False and return_structured=True, returns all transactions
                     (not deduplicated by ticker). Useful for cluster detection.
    """
    return get_insider_buying_screener(
        transaction_type=transaction_type,
        lookback_days=lookback_days,
        min_value=min_value,
        top_n=top_n,
        return_structured=return_structured,
        deduplicate=deduplicate,
    )
