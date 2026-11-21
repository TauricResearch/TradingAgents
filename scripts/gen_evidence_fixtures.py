#!/usr/bin/env python3
"""Generate the 31 evidence fixtures for FR-01 / INV-02 tests.

Deterministic: re-running produces byte-identical files.

Data shapes follow the real providers of the baseline (commit 9fa1196):
  - yahoo_news        : providerPublishTime (epoch) / pubDate (string)
  - sec_edgar         : filing date, day granularity
  - yahoo_fundamentals: period end + availability day
  - stocktwits        : created_at, ISO 8601 with offset
  - reddit            : created_utc, epoch seconds
  - fred              : observation date, day granularity
  - yfinance_bar      : Date only, no time component (the key hazard)
  - insider_trade     : filing date, day granularity

Run: python scripts/gen_evidence_fixtures.py
"""

from __future__ import annotations

import calendar
import hashlib
import json
from datetime import datetime
from pathlib import Path

AS_OF = "2026-11-11T00:00:00Z"
TICKER = "AAPL"
FETCHED = "2026-11-11T00:05:00Z"

OUT = Path(__file__).resolve().parents[1] / "test" / "offline" / "evidence" / "fixtures"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def epoch(iso: str) -> int:
    return calendar.timegm(datetime.fromisoformat(iso.replace("Z", "+00:00")).utctimetuple())


# ---------------------------------------------------------------- item builders


def news(cid: str, uri: str, published: str | None, text: str, *, field="providerPublishTime",
         gran="second", trust="secondary", **extra):
    d = {
        "case_local_id": cid,
        "source_type": "yahoo_news",
        "source_uri": uri,
        "raw_time_field": field,
        "time_granularity": gran,
        "published_at": published,
        "fetched_at": FETCHED,
        "excerpt": text,
        "content_hash": sha(text),
        "raw_value": None,
        "trust_label": trust,
    }
    if published is None:
        d.pop("published_at")
    d.update(extra)
    return d


def edgar(cid: str, uri: str, filed: str, text: str, *, form="10-Q", accn="", value=None):
    return {
        "case_local_id": cid,
        "source_type": "sec_edgar",
        "source_uri": uri,
        "raw_time_field": "filed",
        "time_granularity": "day",
        "published_at": filed,
        "fetched_at": FETCHED,
        "excerpt": text,
        "content_hash": sha(text),
        "raw_value": value,
        "trust_label": "primary",
        "form": form,
        "accession": accn,
    }


def fundamentals(cid: str, uri: str, available: str, text: str, value: float, *, period_end="2026-09-30"):
    return {
        "case_local_id": cid,
        "source_type": "yahoo_fundamentals",
        "source_uri": uri,
        "raw_time_field": "date",
        "time_granularity": "day",
        "published_at": available,
        "fetched_at": FETCHED,
        "excerpt": text,
        "content_hash": sha(text),
        "raw_value": value,
        "trust_label": "primary",
        "period_end": period_end,
    }


def stocktwits(cid: str, uri: str, created: str | None, text: str, *, field="created_at"):
    d = {
        "case_local_id": cid,
        "source_type": "stocktwits",
        "source_uri": uri,
        "raw_time_field": field,
        "time_granularity": "second",
        "published_at": created,
        "fetched_at": FETCHED,
        "excerpt": text,
        "content_hash": sha(text),
        "raw_value": None,
        "trust_label": "secondary",
    }
    if created is None:
        d.pop("published_at")
    return d


def reddit(cid: str, uri: str, created_iso: str | None, text: str):
    d = {
        "case_local_id": cid,
        "source_type": "reddit",
        "source_uri": uri,
        "raw_time_field": "created_utc",
        "time_granularity": "second",
        "created_utc": epoch(created_iso) if created_iso else None,
        "published_at": created_iso,
        "fetched_at": FETCHED,
        "excerpt": text,
        "content_hash": sha(text),
        "raw_value": None,
        "trust_label": "secondary",
    }
    if created_iso is None:
        d.pop("published_at")
    return d


def fred(cid: str, uri: str, day: str, text: str, value: float, series="DFF"):
    return {
        "case_local_id": cid,
        "source_type": "fred",
        "source_uri": uri,
        "raw_time_field": "date",
        "time_granularity": "day",
        "published_at": day,
        "fetched_at": FETCHED,
        "excerpt": text,
        "content_hash": sha(text),
        "raw_value": value,
        "trust_label": "primary",
        "series": series,
    }


def bar(cid: str, uri: str, day: str, ohlc: dict):
    text = f"OHLC {day}: open {ohlc['open']}, high {ohlc['high']}, low {ohlc['low']}, close {ohlc['close']}"
    return {
        "case_local_id": cid,
        "source_type": "yfinance_bar",
        "source_uri": uri,
        "raw_time_field": "Date",
        "time_granularity": "date_only",
        "published_at": day,
        "fetched_at": FETCHED,
        "excerpt": text,
        "content_hash": sha(text),
        "raw_value": ohlc,
        "trust_label": "primary",
    }


def insider(cid: str, uri: str, filed: str, text: str, shares=12000):
    return {
        "case_local_id": cid,
        "source_type": "insider_trade",
        "source_uri": uri,
        "raw_time_field": "filed",
        "time_granularity": "day",
        "published_at": filed,
        "fetched_at": FETCHED,
        "excerpt": text,
        "content_hash": sha(text),
        "raw_value": shares,
        "trust_label": "primary",
    }


CASES: list[dict] = []


# ---------------------------------------------------------------- 4.1 normal (E-01 .. E-12)


CASES.append({
    "case_id": "E-01",
    "purpose": "单一新闻源正常入包",
    "source_type": "yahoo_news", "raw_time_field": "providerPublishTime", "time_granularity": "second",
    "as_of": AS_OF, "provider_behavior": "normal",
    "items": [news("E-01-1", "yahoo-news://8f2c1d", "2026-11-10T13:05:00Z",
                   "Apple supplier orders point to a stronger iPhone build in the March quarter.")],
    "expected": {"admitted": ["E-01-1"], "excluded": [], "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-02",
    "purpose": "SEC EDGAR 8-K 按申报日入包",
    "source_type": "sec_edgar", "raw_time_field": "filed", "time_granularity": "day",
    "as_of": AS_OF, "provider_behavior": "normal",
    "items": [edgar("E-02-1", "sec-edgar://CIK0000320193/0000320193-26-000010", "2026-11-09",
                    "8-K: current report filed on amendment to a supply agreement.", form="8-K",
                    accn="0000320193-26-000010")],
    "expected": {"admitted": ["E-02-1"], "excluded": [], "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-03",
    "purpose": "财报按期次入包，期次与可得日分开记录",
    "source_type": "yahoo_fundamentals", "raw_time_field": "date", "time_granularity": "day",
    "as_of": AS_OF, "provider_behavior": "normal",
    "items": [fundamentals("E-03-1", "yahoo-fin://AAPL/fundamentals/2026Q3", "2026-10-30",
                           "Quarterly revenue 94,930 (USD millions), period ended 2026-09-30.", 94930.0)],
    "expected": {"admitted": ["E-03-1"], "excluded": [], "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-04",
    "purpose": "舆情帖子带秒级时间戳入包",
    "source_type": "stocktwits", "raw_time_field": "created_at", "time_granularity": "second",
    "as_of": AS_OF, "provider_behavior": "normal",
    "items": [stocktwits("E-04-1", "stocktwits://msg/4712001", "2026-11-10T09:12:00Z",
                         "Bullish: services margin looks like it is inflecting.")],
    "expected": {"admitted": ["E-04-1"], "excluded": [], "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-05",
    "purpose": "Reddit 帖子以 epoch 时间戳入包",
    "source_type": "reddit", "raw_time_field": "created_utc", "time_granularity": "second",
    "as_of": AS_OF, "provider_behavior": "normal",
    "items": [reddit("E-05-1", "reddit://r/stocks/t3_1kv9ab", "2026-11-10T12:15:00Z",
                     "Thread: who is actually pricing the services growth here?")],
    "expected": {"admitted": ["E-05-1"], "excluded": [], "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-06",
    "purpose": "FRED 宏观观测点入包",
    "source_type": "fred", "raw_time_field": "date", "time_granularity": "day",
    "as_of": AS_OF, "provider_behavior": "normal",
    "items": [fred("E-06-1", "fred://DFF/2026-10-31", "2026-10-31",
                   "DFF effective rate 4.33 percent on 2026-10-31.", 4.33)],
    "expected": {"admitted": ["E-06-1"], "excluded": [], "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-07",
    "purpose": "行情 bar 只有 Date 无时刻；as_of 的 UTC 日期不早于该日即可用（同日或更早可用）",
    "source_type": "yfinance_bar", "raw_time_field": "Date", "time_granularity": "date_only",
    "as_of": AS_OF, "provider_behavior": "normal",
    "items": [bar("E-07-1", "yfinance://AAPL/2026-11-10", "2026-11-10",
                  {"open": 227.10, "high": 230.42, "low": 226.85, "close": 229.87})],
    "expected": {"admitted": ["E-07-1"], "excluded": [], "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-08",
    "purpose": "两来源同事件并存，不互相覆盖",
    "source_type": "yahoo_news", "raw_time_field": "pubDate", "time_granularity": "minute",
    "as_of": AS_OF, "provider_behavior": "normal",
    "items": [
        news("E-08-1", "yahoo-news://8f2c1d", "2026-11-10T13:05:00Z",
             "Apple supplier orders point to a stronger iPhone build in the March quarter."),
        news("E-08-2", "reuters://2026-11-10/aapl-supplier-orders", "2026-11-10T13:20:00Z",
             "Suppliers see Apple lifting March-quarter build plans, two people say.", field="pubDate"),
    ],
    "expected": {"admitted": ["E-08-1", "E-08-2"], "excluded": [], "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-09",
    "purpose": "内部人交易按申报日计（发生日与申报日分开）",
    "source_type": "insider_trade", "raw_time_field": "filed", "time_granularity": "day",
    "as_of": AS_OF, "provider_behavior": "normal",
    "items": [insider("E-09-1", "sec-edgar://CIK0000320193/form4/2026-10-20", "2026-10-20",
                      "Form 4: officer sold 12,000 shares on 2026-10-16, filed 2026-10-20.")],
    "expected": {"admitted": ["E-09-1"], "excluded": [], "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-10",
    "purpose": "带 excerpt 的条目，content_hash 可由正文复算",
    "source_type": "yahoo_news", "raw_time_field": "providerPublishTime", "time_granularity": "second",
    "as_of": AS_OF, "provider_behavior": "normal",
    "items": [news("E-10-1", "yahoo-news://a71b09", "2026-11-10T08:40:00Z",
                   "Apple said it expects services revenue to grow at a double-digit rate.")],
    "expected": {"admitted": ["E-10-1"], "excluded": [], "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-11",
    "purpose": "非 UTC 源（香港时间 17:00 = 09:00Z）归一后入包",
    "source_type": "yahoo_news", "raw_time_field": "pubDate", "time_granularity": "second",
    "as_of": AS_OF, "provider_behavior": "normal",
    "items": [news("E-11-1", "hkexnews://2026-11-10/e-1", "2026-11-10T17:00:00+08:00",
                   "Hong Kong filing notice published in local time.", field="pubDate")],
    "expected": {"admitted": ["E-11-1"], "excluded": [], "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-12",
    "purpose": "混合包：6 条不同来源全部正常，pack_hash 可复算",
    "source_type": "mixed", "raw_time_field": "mixed", "time_granularity": "mixed",
    "as_of": AS_OF, "provider_behavior": "normal",
    "items": [
        news("E-12-1", "yahoo-news://c3d8e1", "2026-11-10T11:00:00Z",
             "Apple shares rose after a broker upgrade on services estimates."),
        edgar("E-12-2", "sec-edgar://CIK0000320193/0000320193-26-000007", "2026-11-06",
              "10-Q: quarterly report for period ended 2026-09-30.", accn="0000320193-26-000007"),
        stocktwits("E-12-3", "stocktwits://msg/4711888", "2026-11-10T07:45:00Z",
                   "Watching the 230 level, volume is thin."),
        reddit("E-12-4", "reddit://r/stocks/t3_1kv91x", "2026-11-09T22:10:00Z",
               "Anyone else think services is the only growth story left?"),
        fred("E-12-5", "fred://DFF/2026-10-30", "2026-10-30",
             "DFF effective rate 4.33 percent on 2026-10-30.", 4.33),
        bar("E-12-6", "yfinance://AAPL/2026-11-09", "2026-11-09",
            {"open": 225.40, "high": 228.10, "low": 224.90, "close": 227.55}),
    ],
    "expected": {"admitted": ["E-12-1", "E-12-2", "E-12-3", "E-12-4", "E-12-5", "E-12-6"],
                 "excluded": [], "conflict_groups": [], "outcome": "PACK"},
})


# ---------------------------------------------------------------- 4.2 future (E-13 .. E-16, E-28)


CASES.append({
    "case_id": "E-13",
    "purpose": "as_of 次日发布的新闻必须排除",
    "source_type": "yahoo_news", "raw_time_field": "providerPublishTime", "time_granularity": "second",
    "as_of": AS_OF, "provider_behavior": "future_item",
    "items": [news("E-13-1", "yahoo-news://d41f77", "2026-11-12T09:00:00Z",
                   "Apple announced a new services bundle at its developer event.")],
    "expected": {"admitted": [], "excluded": [{"case_local_id": "E-13-1", "reason_code": "FUTURE_DATA"}],
                 "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-14",
    "purpose": "as_of 之后才申报的文件必须排除",
    "source_type": "sec_edgar", "raw_time_field": "filed", "time_granularity": "day",
    "as_of": AS_OF, "provider_behavior": "future_item",
    "items": [edgar("E-14-1", "sec-edgar://CIK0000320193/0000320193-26-000021", "2026-11-15",
                    "10-K: annual report for fiscal year ended 2026-09-30.", form="10-K",
                    accn="0000320193-26-000021")],
    "expected": {"admitted": [], "excluded": [{"case_local_id": "E-14-1", "reason_code": "FUTURE_DATA"}],
                 "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-15",
    "purpose": "同一 as_of 日晚 30 分钟的帖子必须排除",
    "source_type": "stocktwits", "raw_time_field": "created_at", "time_granularity": "second",
    "as_of": AS_OF, "provider_behavior": "future_item",
    "items": [stocktwits("E-15-1", "stocktwits://msg/4712002", "2026-11-11T00:30:00Z",
                         "Just saw the after-hours print, this changes the setup.")],
    "expected": {"admitted": [], "excluded": [{"case_local_id": "E-15-1", "reason_code": "FUTURE_DATA"}],
                 "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-16",
    "purpose": "未来日期的宏观观测点必须排除",
    "source_type": "fred", "raw_time_field": "date", "time_granularity": "day",
    "as_of": AS_OF, "provider_behavior": "future_item",
    "items": [fred("E-16-1", "fred://DFF/2026-11-13", "2026-11-13",
                   "DFF effective rate 4.30 percent on 2026-11-13.", 4.30)],
    "expected": {"admitted": [], "excluded": [{"case_local_id": "E-16-1", "reason_code": "FUTURE_DATA"}],
                 "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-28",
    "purpose": "时区边界确定性用例：00:30Z 的帖子排除，结果不受运行时刻影响",
    "source_type": "stocktwits", "raw_time_field": "created_at", "time_granularity": "second",
    "as_of": AS_OF, "provider_behavior": "future_item",
    "items": [stocktwits("E-28-1", "stocktwits://msg/4712005", "2026-11-11T00:30:00Z",
                         "Post published half an hour after the as-of cutoff.")],
    "expected": {"admitted": [], "excluded": [{"case_local_id": "E-28-1", "reason_code": "FUTURE_DATA"}],
                 "conflict_groups": [], "outcome": "PACK"},
})


# ---------------------------------------------------------------- 4.3 undated (E-17 .. E-20)


CASES.append({
    "case_id": "E-17",
    "purpose": "新闻缺 published_at：标不可用，但必须出现在 excluded_items（不得静默丢弃）",
    "source_type": "yahoo_news", "raw_time_field": "none", "time_granularity": "none",
    "as_of": AS_OF, "provider_behavior": "undated",
    "items": [news("E-17-1", "yahoo-news://e77a10", None,
                   "Apple supplier commentary carried no publication timestamp.", field="none", gran="none")],
    "expected": {"admitted": [], "excluded": [{"case_local_id": "E-17-1", "reason_code": "EVIDENCE_MISSING"}],
                 "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-18",
    "purpose": "时间串损坏：解析失败要记原因，不得当作有效时间",
    "source_type": "yahoo_news", "raw_time_field": "providerPublishTime", "time_granularity": "second",
    "as_of": AS_OF, "provider_behavior": "malformed_time",
    "items": [news("E-18-1", "yahoo-news://c02b33", "2026-13-45 25:61",
                   "Article whose timestamp field was corrupted upstream.")],
    "expected": {"admitted": [], "excluded": [{"case_local_id": "E-18-1", "reason_code": "INVALID_TIME"}],
                 "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-19",
    "purpose": "有时刻但缺时区：不可假定为 UTC，标不可用",
    "source_type": "stocktwits", "raw_time_field": "created_at", "time_granularity": "second",
    "as_of": AS_OF, "provider_behavior": "malformed_time",
    "items": [stocktwits("E-19-1", "stocktwits://msg/4711999", "2026-11-10T09:00:00",
                         "Timestamp has no UTC offset, ordering against as_of is undefined.")],
    "expected": {"admitted": [], "excluded": [{"case_local_id": "E-19-1", "reason_code": "INVALID_TIME"}],
                 "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-20",
    "purpose": "元数据被剥离且为唯一支撑：证据不足应返回 REVIEW + missing_evidence",
    "source_type": "yahoo_news", "raw_time_field": "none", "time_granularity": "none",
    "as_of": AS_OF, "provider_behavior": "undated",
    "items": [news("E-20-1", "yahoo-news://b19d4c", None,
                   "Body text survived but the publication metadata was stripped.",
                   field="none", gran="none")],
    "expected": {"admitted": [], "excluded": [{"case_local_id": "E-20-1", "reason_code": "EVIDENCE_MISSING"}],
                 "conflict_groups": [], "outcome": "REVIEW", "missing_evidence": True},
})


# ---------------------------------------------------------------- 4.4 duplicate / conflict (E-21 .. E-23)


CASES.append({
    "case_id": "E-21",
    "purpose": "同一 uri 同一时间被抓两次：去重只留一条 canonical",
    "source_type": "yahoo_news", "raw_time_field": "providerPublishTime", "time_granularity": "second",
    "as_of": AS_OF, "provider_behavior": "duplicate",
    "items": [
        news("E-21-1", "yahoo-news://8f2c1d", "2026-11-10T13:05:00Z",
             "Apple supplier orders point to a stronger iPhone build in the March quarter."),
        news("E-21-2", "yahoo-news://8f2c1d", "2026-11-10T13:05:00Z",
             "Apple supplier orders point to a stronger iPhone build in the March quarter."),
    ],
    "expected": {"admitted": ["E-21-1"], "excluded": [], "conflict_groups": [], "outcome": "PACK",
                 "note": "两个 item 内容完全相同；E-21-2 是同一抓取的重复副本，去重后只应出现一次"},
})

CASES.append({
    "case_id": "E-22",
    "purpose": "两源同一指标数值冲突：两条都保留并标记 conflict_group，不静默覆盖",
    "source_type": "yahoo_fundamentals", "raw_time_field": "date", "time_granularity": "day",
    "as_of": AS_OF, "provider_behavior": "conflict",
    "items": [
        fundamentals("E-22-1", "yahoo-fin://AAPL/fundamentals/2026Q3", "2026-10-30",
                     "Quarterly revenue 118,400 (USD millions).", 118400.0),
        fundamentals("E-22-2", "alpha-vantage://AAPL/income/2026Q3", "2026-10-31",
                     "Quarterly revenue 121,700 (USD millions).", 121700.0),
    ],
    "expected": {"admitted": ["E-22-1", "E-22-2"], "excluded": [],
                 "conflict_groups": [{"conflict_group": "aapl-revenue-2026Q3",
                                      "members": ["E-22-1", "E-22-2"]}],
                 "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-23",
    "purpose": "转载篡改 excerpt：按 source_uri + hash 判为篡改，保留原版",
    "source_type": "yahoo_news", "raw_time_field": "providerPublishTime", "time_granularity": "second",
    "as_of": AS_OF, "provider_behavior": "tampered_hash",
    "items": [
        news("E-23-1", "yahoo-news://8f2c1d", "2026-11-10T13:05:00Z",
             "Apple supplier orders point to a stronger iPhone build in the March quarter."),
        news("E-23-2", "yahoo-news://8f2c1d", "2026-11-10T13:05:00Z",
             "Apple supplier orders point to a much weaker iPhone build in the March quarter.",
             content_hash=sha("Apple supplier orders point to a stronger iPhone build in the March quarter.")),
    ],
    "expected": {"admitted": ["E-23-1"],
                 "excluded": [{"case_local_id": "E-23-2", "reason_code": "INTEGRITY_VIOLATION"}],
                 "conflict_groups": [], "outcome": "PACK"},
})


# ---------------------------------------------------------------- 4.5 unreachable (E-24 .. E-26)


CASES.append({
    "case_id": "E-24",
    "purpose": "provider 返回 429：标不可用并记 VENDOR_UNAVAILABLE，不得冒充新鲜数据",
    "source_type": "yahoo_news", "raw_time_field": "none", "time_granularity": "none",
    "as_of": AS_OF, "provider_behavior": "rate_limited",
    "items": [],
    "provider_error": {"status": 429, "detail": "Too Many Requests"},
    "expected": {"admitted": [],
                 "excluded": [{"case_local_id": "provider", "reason_code": "VENDOR_UNAVAILABLE"}],
                 "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-25",
    "purpose": "provider 超时：标不可用，不计入成功证据",
    "source_type": "yahoo_news", "raw_time_field": "none", "time_granularity": "none",
    "as_of": AS_OF, "provider_behavior": "timeout",
    "items": [],
    "provider_error": {"status": "timeout", "detail": "connect timeout after 30s"},
    "expected": {"admitted": [],
                 "excluded": [{"case_local_id": "provider", "reason_code": "VENDOR_UNAVAILABLE"}],
                 "conflict_groups": [], "outcome": "PACK"},
})

CASES.append({
    "case_id": "E-26",
    "purpose": "全离线只有旧缓存：必须标 stale，不得伪装成新数据",
    "source_type": "cache", "raw_time_field": "providerPublishTime", "time_granularity": "second",
    "as_of": AS_OF, "provider_behavior": "offline_cache",
    "items": [{
        "case_local_id": "E-26-1",
        "source_type": "cache",
        "source_uri": "yahoo-news://cached-8f2c1d",
        "raw_time_field": "providerPublishTime",
        "time_granularity": "second",
        "published_at": "2026-09-19T13:05:00Z",
        "fetched_at": "2026-09-20T02:00:00Z",
        "excerpt": "Cached copy of the March-quarter supplier story.",
        "content_hash": sha("Cached copy of the March-quarter supplier story."),
        "raw_value": None,
        "trust_label": "secondary",
    }],
    "expected": {"admitted": [], "excluded": [{"case_local_id": "E-26-1", "reason_code": "STALE_DATA"}],
                 "conflict_groups": [], "outcome": "PACK",
                 "note": "条目可以被读出来，但 availability 必须是 stale，不得是 available"},
})


# ---------------------------------------------------------------- 4.6 boundary admitted (E-27)


CASES.append({
    "case_id": "E-27",
    "purpose": "临界 admitted：23:30Z 早于 00:00Z 截止点，归一后入包",
    "source_type": "yahoo_news", "raw_time_field": "providerPublishTime", "time_granularity": "second",
    "as_of": AS_OF, "provider_behavior": "normal",
    "items": [news("E-27-1", "yahoo-news://9a2f01", "2026-11-10T23:30:00Z",
                   "Late-evening story published 30 minutes before the as-of cutoff.")],
    "expected": {"admitted": ["E-27-1"], "excluded": [], "conflict_groups": [], "outcome": "PACK"},
})


# ---------------------------------------------------------------- 4.7 forged / tampered (E-29, E-30)


CASES.append({
    "case_id": "E-29",
    "purpose": "claim 引用不存在的 evidence_id：引用校验必须失败",
    "source_type": "yahoo_news", "raw_time_field": "providerPublishTime", "time_granularity": "second",
    "as_of": AS_OF, "provider_behavior": "missing_reference",
    "items": [news("E-29-1", "yahoo-news://7f10aa", "2026-11-10T10:00:00Z",
                   "Story that a claim will cite incorrectly.")],
    "claim": {"claim_id": "C-29", "text": "Services growth accelerated in the September quarter.",
              "evidence_ids": ["E-29-1", "E-99-does-not-exist"]},
    "expected": {"admitted": ["E-29-1"], "excluded": [],
                 "conflict_groups": [], "outcome": "ERROR", "error_code": "INVALID_CITATION"},
})

CASES.append({
    "case_id": "E-30",
    "purpose": "excerpt 在 hash 之后被改：拒绝入包并记完整性事件",
    "source_type": "yahoo_news", "raw_time_field": "providerPublishTime", "time_granularity": "second",
    "as_of": AS_OF, "provider_behavior": "tampered_hash",
    "items": [news("E-30-1", "yahoo-news://21c0be", "2026-11-10T08:00:00Z",
                   "Apple cut its March-quarter build plans, the excerpt now claims.",
                   content_hash=sha("Apple raised its March-quarter build plans."))],
    "expected": {"admitted": [],
                 "excluded": [{"case_local_id": "E-30-1", "reason_code": "INTEGRITY_VIOLATION"}],
                 "conflict_groups": [], "outcome": "PACK", "integrity_event": True},
})


# ---------------------------------------------------------------- 4.8 boundary equal (E-31)


CASES.append({
    "case_id": "E-31",
    "purpose": "临界 admitted：date_only 日期恰等于 as_of 的 UTC 日期，as_of 为闭区间",
    "source_type": "yfinance_bar", "raw_time_field": "Date", "time_granularity": "date_only",
    "as_of": AS_OF, "provider_behavior": "boundary_equal",
    "items": [bar("E-31-1", "yfinance://AAPL/2026-11-11", "2026-11-11",
                  {"open": 229.87, "high": 231.20, "low": 228.90, "close": 230.55})],
    "expected": {"admitted": ["E-31-1"], "excluded": [], "conflict_groups": [], "outcome": "PACK",
                 "note": "date_only 只给日期；该日包含 as_of，不得判为 INVALID_TIME 或 FUTURE_DATA"},
})


AVAILABILITY_BY_REASON = {
    "FUTURE_DATA": "unavailable",
    "EVIDENCE_MISSING": "unavailable",
    "INVALID_TIME": "unavailable",
    "STALE_DATA": "stale",
    "VENDOR_UNAVAILABLE": "unreachable",
    "INTEGRITY_VIOLATION": "unavailable",
    "INVALID_CITATION": "available",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        # availability 是状态，reason_code 是原因；两者不互相替代
        for ex in case["expected"].get("excluded", []):
            ex.setdefault("availability", AVAILABILITY_BY_REASON[ex["reason_code"]])
        # claim 用 case_local_id 书写，正式 id 由服务组合
        if "claim" in case:
            case["claim"].setdefault(
                "note", "evidence_ids 以 case_local_id 书写；正式 evidence_id 由服务按 <run_id>-<case_local_id> 生成")

        path = OUT / f"{case['case_id']}.json"
        path.write_text(json.dumps(case, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
                        encoding="utf-8")
    print(f"wrote {len(CASES)} fixtures to {OUT}")


if __name__ == "__main__":
    main()
