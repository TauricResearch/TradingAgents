"""雪球社区讨论帖抓取模块。

通过雪球公开 API 获取 A 股个股讨论帖，用于情感分析等下游任务。
雪球接口需要先访问主页获取匿名 cookie（``xq_a_token``），然后才能
调用搜索 API。

返回格式化纯文本块，可直接注入 prompt。降级处理——遇到任何网络或解析
错误时返回占位符字符串，调用方无需特殊处理缺失数据。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

# 雪球 API 地址
_HOME_URL = "https://xueqiu.com"
_SEARCH_API = "https://xueqiu.com/query/v1/search/status.json"

# 模拟浏览器 User-Agent，防止被反爬
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_TIMEOUT = 10  # 请求超时秒数
_POST_COUNT = 20  # 每次拉取帖子数


def _convert_ticker(ticker: str) -> str:
    """将常见 A 股代码格式转为雪球搜索关键词。

    支持的输入格式:
    - ``600519.SH`` / ``000001.SZ`` -> ``SH600519`` / ``SZ000001``
    - ``SH600519`` -> 原样返回
    - ``600519`` -> 原样返回（纯数字）
    """
    # 匹配 "数字.交易所" 格式，如 600519.SH、000001.SZ
    m = re.match(r"^(\d{6})\.(SH|SZ|BJ)$", ticker.upper())
    if m:
        code, exchange = m.group(1), m.group(2)
        return f"{exchange}{code}"
    return ticker


def _get_session() -> requests.Session:
    """创建带匿名 cookie 的请求会话。

    访问雪球主页以获取 ``xq_a_token`` 等必要 cookie，
    后续 API 调用需携带这些 cookie 才能正常返回数据。
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": _UA,
        "Accept": "application/json, text/plain, */*",
        "Referer": _HOME_URL,
    })
    # 访问主页获取匿名 cookie
    try:
        session.get(_HOME_URL, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        logger.warning("雪球主页访问失败，无法获取 cookie: %s", exc)
    return session


def _format_timestamp(ts: int | float | None) -> str:
    """将雪球毫秒时间戳转为可读日期字符串。"""
    if not ts:
        return "?"
    try:
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError, OverflowError):
        return "?"


def _strip_html(text: str) -> str:
    """移除 HTML 标签，返回纯文本。"""
    return re.sub(r"<[^>]+>", "", text)


def fetch_xueqiu_posts(ticker: str, count: int = _POST_COUNT) -> str:
    """获取雪球社区中关于 ``ticker`` 的讨论帖，返回格式化纯文本。

    Parameters
    ----------
    ticker : str
        股票代码，支持 ``600519.SH``、``SH600519``、``600519`` 等格式。
    count : int
        拉取帖子数量，默认 20。

    Returns
    -------
    str
        格式化的讨论帖纯文本；网络或解析错误时返回降级占位符。
    """
    xq_keyword = _convert_ticker(ticker)

    # 创建带 cookie 的会话
    try:
        session = _get_session()
    except Exception as exc:
        logger.warning("雪球会话初始化失败: %s", exc)
        return f"[Xueqiu data unavailable for {ticker}]"

    # 调用搜索 API
    params = {
        "q": xq_keyword,
        "count": count,
        "sort": "time",
    }
    try:
        resp = session.get(_SEARCH_API, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning("雪球搜索 API 请求失败 (%s): %s", xq_keyword, exc)
        return f"[Xueqiu data unavailable for {ticker}]"
    except (ValueError, KeyError) as exc:
        logger.warning("雪球搜索 API 响应解析失败 (%s): %s", xq_keyword, exc)
        return f"[Xueqiu data unavailable for {ticker}]"

    # 提取帖子列表
    posts = data.get("list") or []
    if not posts:
        return f"[Xueqiu data unavailable for {ticker}]"

    # 格式化输出
    lines: list[str] = [
        f"=== 雪球讨论 ({ticker}) ===",
        f"共获取 {len(posts)} 条讨论",
        "",
    ]

    for idx, post in enumerate(posts, start=1):
        # 标题或内容摘要
        title = (post.get("title") or "").strip()
        description = (post.get("description") or post.get("text") or "").strip()
        description = _strip_html(description)

        # 优先用标题，无标题则用内容摘要
        display_text = title if title else description
        display_text = display_text.replace("\n", " ").strip()
        if len(display_text) > 200:
            display_text = display_text[:200] + "…"
        if not display_text:
            display_text = "<无内容>"

        # 互动数据
        likes = post.get("like_count", 0) or 0
        comments = post.get("reply_count", 0) or 0
        created = post.get("created_at")
        created_str = _format_timestamp(created)

        lines.append(f"{idx}. [{display_text}]")
        lines.append(f"   点赞: {likes} | 评论: {comments} | 时间: {created_str}")
        lines.append("")

    return "\n".join(lines).rstrip()
