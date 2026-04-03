from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta

from .exceptions import DataVendorUnavailable


def _parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d")


def _ensure_opencli() -> str:
    binary = shutil.which("opencli-rs")
    if not binary:
        raise DataVendorUnavailable("opencli-rs is not installed or not on PATH.")
    return binary


def _run_opencli(args: list[str]) -> list[dict]:
    binary = _ensure_opencli()
    try:
        result = subprocess.run(
            [binary, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise DataVendorUnavailable(f"opencli-rs execution failed: {exc}") from exc

    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise DataVendorUnavailable(f"opencli-rs command failed: {stderr}")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise DataVendorUnavailable("opencli-rs returned non-JSON output.") from exc

    if not isinstance(payload, list):
        raise DataVendorUnavailable("opencli-rs returned an unexpected payload format.")

    return payload


def _safe_run_opencli(args: list[str]) -> tuple[list[dict], str | None]:
    try:
        return _run_opencli(args), None
    except DataVendorUnavailable as exc:
        return [], str(exc)


def _format_block(title: str, records: list[str]) -> str:
    if not records:
        return f"### {title}\nNo results."
    return f"### {title}\n" + "\n\n".join(records)


def _dedupe_records(items: list[dict], keys: tuple[str, ...]) -> list[dict]:
    seen: set[str] = set()
    output: list[dict] = []
    for item in items:
        identity = " | ".join(str(item.get(key, "")).strip() for key in keys).strip()
        if not identity or identity in seen:
            continue
        seen.add(identity)
        output.append(item)
    return output


def _clean_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _symbol_without_suffix(symbol: str) -> str:
    clean = _clean_symbol(symbol)
    return clean.split(".", 1)[0]


def _resolve_company_aliases(ticker: str) -> list[str]:
    aliases: list[str] = []

    try:
        from .tushare import _classify_market, _get_pro_client, _normalize_ts_code

        ts_code = _normalize_ts_code(ticker)
        market = _classify_market(ts_code)
        pro = _get_pro_client()

        if market == "a_share":
            basic = pro.stock_basic(ts_code=ts_code, fields="ts_code,name")
        elif market == "hk":
            basic = pro.hk_basic(ts_code=ts_code)
        else:
            basic = pro.us_basic(ts_code=ts_code)

        if basic is not None and not basic.empty:
            row = basic.iloc[0]
            for field in ("name", "fullname", "enname"):
                value = row.get(field)
                if value:
                    aliases.append(str(value).strip())
    except Exception:
        pass

    aliases.extend([_clean_symbol(ticker), _symbol_without_suffix(ticker)])

    expanded_aliases: list[str] = []
    for alias in aliases:
        alias = alias.strip()
        if not alias:
            continue
        expanded_aliases.append(alias)
        if alias.endswith("股份有限公司"):
            short_alias = alias[: -len("股份有限公司")].strip()
            if short_alias:
                expanded_aliases.append(short_alias)
        if alias.endswith("有限公司"):
            short_alias = alias[: -len("有限公司")].strip()
            if short_alias:
                expanded_aliases.append(short_alias)

    seen: set[str] = set()
    result: list[str] = []
    for alias in expanded_aliases:
        if alias not in seen:
            seen.add(alias)
            result.append(alias)
    return result


def _build_google_queries(ticker: str) -> list[str]:
    aliases = _resolve_company_aliases(ticker)
    queries: list[str] = []
    for alias in aliases:
        queries.append(f"{alias} stock")
        queries.append(alias)
    return queries


def _collect_google_news(ticker: str, limit: int = 8) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    errors: list[str] = []

    for query in _build_google_queries(ticker):
        payload, error = _safe_run_opencli(
            ["google", "news", query, "--limit", str(limit), "--format", "json"]
        )
        if error:
            errors.append(f"{query}: {error}")
            continue
        items.extend(payload)
        if len(_dedupe_records(items, ("url", "title"))) >= limit:
            break

    return _dedupe_records(items, ("url", "title"))[:limit], errors


def _collect_google_search_results(ticker: str, limit: int = 8) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    errors: list[str] = []

    for query in _build_google_queries(ticker):
        payload, error = _safe_run_opencli(
            ["google", "search", query, "--lang", "zh", "--limit", str(limit), "--format", "json"]
        )
        if error:
            errors.append(f"{query}: {error}")
            continue
        items.extend(payload)
        if len(_dedupe_records(items, ("url", "title"))) >= limit:
            break

    return _dedupe_records(items, ("url", "title"))[:limit], errors


def _collect_xueqiu_results(ticker: str, limit: int = 8) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    errors: list[str] = []

    for keyword in _resolve_company_aliases(ticker):
        payload, error = _safe_run_opencli(
            ["xueqiu", "search", keyword, "--limit", str(limit), "--format", "json"]
        )
        if error:
            errors.append(f"{keyword}: {error}")
            continue
        items.extend(payload)
        if len(_dedupe_records(items, ("symbol", "name"))) >= limit:
            break

    return _dedupe_records(items, ("symbol", "name"))[:limit], errors


def _collect_weibo_results(ticker: str, limit: int = 8) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    errors: list[str] = []

    for keyword in _resolve_company_aliases(ticker):
        payload, error = _safe_run_opencli(
            ["weibo", "search", keyword, "--limit", str(limit), "--format", "json"]
        )
        if error:
            errors.append(f"{keyword}: {error}")
            continue
        items.extend(payload)
        if len(_dedupe_records(items, ("url", "text", "word"))) >= limit:
            break

    return _dedupe_records(items, ("url", "text", "word"))[:limit], errors


def _collect_xiaohongshu_results(ticker: str, limit: int = 8) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    errors: list[str] = []

    for keyword in _resolve_company_aliases(ticker):
        payload, error = _safe_run_opencli(
            ["xiaohongshu", "search", keyword, "--limit", str(limit), "--format", "json"]
        )
        if error:
            errors.append(f"{keyword}: {error}")
            continue
        items.extend(payload)
        if len(_dedupe_records(items, ("id", "note_id", "url", "title"))) >= limit:
            break

    return _dedupe_records(items, ("id", "note_id", "url", "title"))[:limit], errors


def _collect_sinafinance_results(ticker: str, limit: int = 8) -> tuple[list[dict], list[str]]:
    aliases = _resolve_company_aliases(ticker)
    payload, error = _safe_run_opencli(
        ["sinafinance", "news", "--type", "1", "--limit", "50", "--format", "json"]
    )
    if error:
        return [], [error]

    filtered: list[dict] = []
    for item in payload:
        haystack = " ".join(
            str(item.get(field, "")).strip()
            for field in ("content", "title", "symbol", "name")
        )
        if any(alias and alias in haystack for alias in aliases):
            filtered.append(item)

    return _dedupe_records(filtered, ("time", "content", "title"))[:limit], []


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    _parse_date(start_date)
    _parse_date(end_date)

    sections: list[str] = []
    errors: list[str] = []

    xueqiu_items, xueqiu_errors = _collect_xueqiu_results(ticker, limit=6)
    errors.extend(xueqiu_errors)
    if xueqiu_items:
        sections.append(
            _format_block(
                "Xueqiu Search",
                [
                    (
                        f"- {item.get('name', item.get('symbol', 'Unknown'))} "
                        f"(symbol: {item.get('symbol', 'Unknown')})"
                    )
                    for item in xueqiu_items
                ],
            )
        )

    weibo_items, weibo_errors = _collect_weibo_results(ticker, limit=6)
    errors.extend(weibo_errors)
    if weibo_items:
        sections.append(
            _format_block(
                "Weibo Search",
                [
                    (
                        f"- {item.get('text', item.get('word', 'No text'))}\n"
                        f"  Link: {item.get('url', '')}"
                    )
                    for item in weibo_items
                ],
            )
        )

    xiaohongshu_items, xiaohongshu_errors = _collect_xiaohongshu_results(ticker, limit=6)
    errors.extend(xiaohongshu_errors)
    if xiaohongshu_items:
        sections.append(
            _format_block(
                "Xiaohongshu Search",
                [
                    (
                        f"- {item.get('title', item.get('desc', 'No title'))}\n"
                        f"  Link: {item.get('url', '')}"
                    )
                    for item in xiaohongshu_items
                ],
            )
        )

    sina_items, sina_errors = _collect_sinafinance_results(ticker, limit=6)
    errors.extend(sina_errors)
    if sina_items:
        sections.append(
            _format_block(
                "Sina Finance A-Share Flash",
                [
                    (
                        f"- {item.get('content', item.get('title', 'No content'))} "
                        f"(time: {item.get('time', 'Unknown')}, views: {item.get('views', 'Unknown')})"
                    )
                    for item in sina_items
                ],
            )
        )

    google_news_items, google_news_errors = _collect_google_news(ticker, limit=6)
    errors.extend(google_news_errors)
    if google_news_items:
        sections.append(
            _format_block(
                "Google News",
                [
                    (
                        f"- {item.get('title', 'No title')} "
                        f"(source: {item.get('source', 'Unknown')}, date: {item.get('date', 'Unknown')})\n"
                        f"  Link: {item.get('url', '')}"
                    )
                    for item in google_news_items
                ],
            )
        )

    google_search_items, google_search_errors = _collect_google_search_results(ticker, limit=6)
    errors.extend(google_search_errors)
    if google_search_items:
        sections.append(
            _format_block(
                "Google Search (ZH)",
                [
                    (
                        f"- {item.get('title', 'No title')}\n"
                        f"  Link: {item.get('url', '')}"
                    )
                    for item in google_search_items
                ],
            )
        )

    if not sections:
        aliases = ", ".join(_resolve_company_aliases(ticker))
        detail = (
            f"No relevant news found via opencli-rs for {ticker} "
            f"between {start_date} and {end_date}. "
            f"Queries tried: {aliases or ticker}."
        )
        if errors:
            detail += f" Source errors: {'; '.join(errors[:3])}."
        return detail

    return f"## {ticker} News and Social Signals, from {start_date} to {end_date}:\n\n" + "\n\n".join(sections)


def get_global_news(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    end_dt = _parse_date(curr_date)
    start_date = (end_dt - timedelta(days=look_back_days)).strftime("%Y-%m-%d")

    sections = []

    google_items = _run_opencli(["google", "news", "--limit", str(limit), "--format", "json"])
    sections.append(
        _format_block(
            "Google News Top Stories",
            [
                (
                    f"- {item.get('title', 'No title')} "
                    f"(source: {item.get('source', 'Unknown')}, date: {item.get('date', 'Unknown')})\n"
                    f"  Link: {item.get('url', '')}"
                )
                for item in google_items[:limit]
            ],
        )
    )

    sina_items = _run_opencli(["sinafinance", "news", "--limit", str(limit), "--format", "json"])
    sections.append(
        _format_block(
            "Sina Finance Flash News",
            [
                (
                    f"- {item.get('content', 'No content')} "
                    f"(time: {item.get('time', 'Unknown')}, views: {item.get('views', 'Unknown')})"
                )
                for item in sina_items[:limit]
            ],
        )
    )

    xueqiu_hot = _run_opencli(["xueqiu", "hot", "--limit", str(min(limit, 8)), "--format", "json"])
    sections.append(
        _format_block(
            "Xueqiu Hot Discussions",
            [
                (
                    f"- {item.get('text', 'No text')} "
                    f"(author: {item.get('author', 'Unknown')}, likes: {item.get('likes', 'Unknown')})\n"
                    f"  Link: {item.get('url', '')}"
                )
                for item in xueqiu_hot[:limit]
            ],
        )
    )

    weibo_hot = _run_opencli(["weibo", "hot", "--limit", str(min(limit, 8)), "--format", "json"])
    sections.append(
        _format_block(
            "Weibo Hot Topics",
            [
                (
                    f"- {item.get('word', 'No topic')} "
                    f"(category: {item.get('category', 'Unknown')}, heat: {item.get('hot_value', 'Unknown')})\n"
                    f"  Link: {item.get('url', '')}"
                )
                for item in weibo_hot[:limit]
            ],
        )
    )

    return f"## Global Market News and Social Signals, from {start_date} to {curr_date}:\n\n" + "\n\n".join(sections)
