"""SimFin data provider for fundamental financial statements."""

import os

import pandas as pd


def _setup():
    """Configure SimFin API key and data directory, return module."""
    import simfin as sf
    sf.set_api_key(os.environ.get("SIMFIN_API_KEY", ""))
    sf.set_data_dir("/tmp/simfin_data/")
    return sf


def _filter_and_format(df: pd.DataFrame, ticker: str, curr_date: str, freq: str, label: str, description: str) -> str:
    """Filter a SimFin DataFrame by ticker and publish date, return formatted string."""
    df["Report Date"] = pd.to_datetime(df["Report Date"], utc=True).dt.normalize()
    df["Publish Date"] = pd.to_datetime(df["Publish Date"], utc=True).dt.normalize()
    curr_date_dt = pd.to_datetime(curr_date, utc=True).normalize()

    filtered = df[(df["Ticker"] == ticker) & (df["Publish Date"] <= curr_date_dt)]

    if filtered.empty:
        return f"No {label} available for {ticker} before {curr_date}."

    latest = filtered.loc[filtered["Publish Date"].idxmax()]
    if "SimFinId" in latest.index:
        latest = latest.drop("SimFinId")

    publish_date = str(latest["Publish Date"])[:10]
    return (
        f"## {freq} {label} for {ticker} released on {publish_date}:\n"
        + str(latest)
        + f"\n\n{description}"
    )


def get_balance_sheet(ticker: str, freq: str, curr_date: str) -> str:
    """Retrieve balance sheet from SimFin."""
    df = _setup().load_balance(variant=freq, market="us")
    return _filter_and_format(
        df, ticker, curr_date, freq, "balance sheet",
        "This includes metadata like reporting dates and currency, share details, and a breakdown of assets, "
        "liabilities, and equity. Assets are grouped as current (liquid items like cash and receivables) and "
        "noncurrent (long-term investments and property). Liabilities are split between short-term obligations "
        "and long-term debts, while equity reflects shareholder funds such as paid-in capital and retained earnings.",
    )


def get_cashflow(ticker: str, freq: str, curr_date: str) -> str:
    """Retrieve cash flow statement from SimFin."""
    df = _setup().load_cashflow(variant=freq, market="us")
    return _filter_and_format(
        df, ticker, curr_date, freq, "cash flow statement",
        "Operating activities show cash generated from core business operations. Investing activities cover asset "
        "acquisitions/disposals. Financing activities include debt transactions and dividend payments. The net change "
        "in cash represents the overall increase or decrease in the company's cash position.",
    )


def get_income_statement(ticker: str, freq: str, curr_date: str) -> str:
    """Retrieve income statement from SimFin."""
    df = _setup().load_income(variant=freq, market="us")
    return _filter_and_format(
        df, ticker, curr_date, freq, "income statement",
        "Starting with Revenue, it shows Cost of Revenue and resulting Gross Profit. Operating Expenses are detailed, "
        "including SG&A, R&D, and Depreciation. The statement shows Operating Income, followed by non-operating items "
        "leading to Pretax Income. After accounting for Income Tax, it concludes with Net Income.",
    )
