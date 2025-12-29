#!/usr/bin/env python3
import argparse
import json
from typing import List, Dict, Any

from tradingagents.dataflows.openai import (
    get_stock_news_openai,
    get_global_news_openai,
)
from tradingagents.dataflows.news_parsers import (
    parse_global_news,
    parse_stock_news,
)


def build_text_from_global_item(item: Dict[str, Any]) -> str:
    parts: List[str] = []
    if item.get("date"):
        parts.append(f"Date: {item['date']}")
    if item.get("headline"):
        parts.append(f"Headline: {item['headline']}")
    if item.get("relevance"):
        parts.append(f"Relevance: {item['relevance']}")
    if item.get("sources"):
        parts.append("Sources: " + ", ".join(item["sources"][:3]))
    return "\n".join(parts).strip()


def build_text_from_stock_item(item: Dict[str, Any]) -> str:
    parts: List[str] = []
    if item.get("title"):
        parts.append(f"Title: {item['title']}")
    if item.get("summary"):
        parts.append(item["summary"])
    if item.get("sources"):
        parts.append("Sources: " + ", ".join(item["sources"][:3]))
    return "\n".join(parts).strip()


def write_json(path: str, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def run_company(ticker: str, start_date: str, end_date: str, out_path: str) -> None:
    raw = get_stock_news_openai(ticker, start_date, end_date)
    items = parse_stock_news(raw)
    rows: List[Dict[str, Any]] = []
    for it in items:
        text = build_text_from_stock_item(it)
        rows.append(
            {
                "text": text,
                "ticker": ticker,
                "start_date": start_date,
                "end_date": end_date,
                "sources": it.get("sources", []),
                # Leave label absent; add later if you want supervised SFT
            }
        )
    write_json(out_path, rows)
    print(f"Wrote {len(rows)} company news items to: {out_path}")


def run_global(curr_date: str, look_back_days: int, limit: int, out_path: str) -> None:
    raw = get_global_news_openai(curr_date, look_back_days=look_back_days, limit=limit)
    items = parse_global_news(raw)
    rows: List[Dict[str, Any]] = []
    for it in items:
        text = build_text_from_global_item(it)
        rows.append(
            {
                "text": text,
                "curr_date": curr_date,
                "look_back_days": look_back_days,
                "sources": it.get("sources", []),
                # Leave label absent; add later if you want supervised SFT
            }
        )
    write_json(out_path, rows)
    print(f"Wrote {len(rows)} global news items to: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Fetch, split, and save news as JSON dataset.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--company", action="store_true", help="Fetch company-specific news")
    mode.add_argument("--global-news", action="store_true", help="Fetch global/macro news")

    parser.add_argument("--ticker", type=str, help="Ticker symbol for company news")
    parser.add_argument("--start-date", type=str, help="Start date YYYY-MM-DD for company news")
    parser.add_argument("--end-date", type=str, help="End date YYYY-MM-DD for company news")

    parser.add_argument("--curr-date", type=str, help="Reference date YYYY-MM-DD for global news")
    parser.add_argument("--look-back-days", type=int, default=7, help="Look-back window for global news")
    parser.add_argument("--limit", type=int, default=5, help="Max number of global items")

    parser.add_argument("--output", type=str, required=True, help="Output JSON path")
    args = parser.parse_args()

    if args.company:
        if not (args.ticker and args.start_date and args.end_date):
            raise SystemExit("For --company, provide --ticker, --start-date, --end-date")
        run_company(args.ticker, args.start_date, args.end_date, args.output)
    else:
        if not args.curr_date:
            raise SystemExit("For --global-news, provide --curr-date")
        run_global(args.curr_date, args.look_back_days, args.limit, args.output)


if __name__ == "__main__":
    main()


