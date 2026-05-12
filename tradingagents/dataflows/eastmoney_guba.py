"""东方财富股吧数据源模块，获取个股讨论帖。

通过东方财富股吧公开 API 获取指定股票的讨论帖列表，包括帖子标题、
阅读量、评论数和发布时间。无需 API Key，公开接口即可访问。

返回格式化的纯文本字符串供 prompt 注入使用。任何异常均优雅降级，
返回占位符字符串而非抛出异常。
"""

from __future__ import annotations

import logging
import re

import requests

logger = logging.getLogger(__name__)

# 东方财富股吧帖子列表 API
_API_URL = (
    "http://guba.eastmoney.com/interface/GetData"
    "?type=0&path=guba%2Flist&ps=20&p=1&code={code}"
)

# 备用 API（移动端接口，结构更稳定）
_API_URL_FALLBACK = (
    "https://gbcdn.dfcfw.com/interfaces/getdata"
    "?type=0&path=guba%2Flist&ps=20&p=1&code={code}"
)

# 模拟浏览器 User-Agent，防止被反爬
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_HEADERS = {
    "User-Agent": _UA,
    "Accept": "application/json, text/plain, */*",
    "Referer": "http://guba.eastmoney.com/",
}

# 请求超时（秒）
_TIMEOUT = 10


def _normalize_ticker(ticker: str) -> str:
    """将各种格式的股票代码统一转换为纯数字代码。

    支持的输入格式：
    - 600519.SH / 000001.SZ -> 600519 / 000001
    - SH600519 / SZ000001  -> 600519 / 000001
    - 600519               -> 600519（保持不变）
    """
    code = ticker.strip().upper()

    # 格式: 600519.SH 或 000001.SZ
    match = re.match(r"^(\d{6})\.[A-Z]{2}$", code)
    if match:
        return match.group(1)

    # 格式: SH600519 或 SZ000001
    match = re.match(r"^[A-Z]{2}(\d{6})$", code)
    if match:
        return match.group(1)

    # 格式: 纯数字
    match = re.match(r"^(\d{6})$", code)
    if match:
        return match.group(1)

    # 无法识别的格式，尝试提取其中的数字部分
    digits = re.findall(r"\d+", code)
    if digits:
        return digits[0]

    return code


def _fetch_posts(code: str) -> list[dict]:
    """从东方财富股吧 API 获取帖子列表，返回解析后的帖子数据。"""
    urls = [_API_URL.format(code=code), _API_URL_FALLBACK.format(code=code)]

    for url in urls:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()

            data = resp.json()

            # API 返回结构：{"re": [...], "ps": 20, ...}
            posts = data.get("re") or []
            if isinstance(posts, list) and len(posts) > 0:
                return posts

        except (
            requests.RequestException,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            logger.warning(
                "东方财富股吧 API 请求失败 [%s]: %s", url, exc
            )
            continue

    return []


def fetch_eastmoney_guba_posts(ticker: str) -> str:
    """获取东方财富股吧中指定股票的讨论帖，返回格式化的纯文本字符串。

    Parameters
    ----------
    ticker : str
        股票代码，支持多种格式（如 600519、600519.SH、SH600519）。

    Returns
    -------
    str
        格式化的讨论帖文本。网络或解析异常时返回占位符字符串。
    """
    code = _normalize_ticker(ticker)

    try:
        posts = _fetch_posts(code)
    except Exception as exc:  # noqa: BLE001
        logger.error("获取股吧数据时发生未预期错误: %s", exc)
        return f"[Eastmoney Guba data unavailable for {ticker}]"

    if not posts:
        return f"[Eastmoney Guba data unavailable for {ticker}]"

    # 格式化输出
    lines: list[str] = []
    lines.append(f"=== 东方财富股吧讨论 ({ticker}) ===")
    lines.append(f"共获取 {len(posts)} 条讨论")
    lines.append("")

    for idx, post in enumerate(posts, 1):
        # 提取帖子信息，兼容不同的字段名
        title = (
            post.get("post_title")
            or post.get("title")
            or post.get("Title")
            or "无标题"
        ).replace("\n", " ").strip()

        read_count = (
            post.get("post_click_count")
            or post.get("click_count")
            or post.get("Rc")
            or 0
        )

        comment_count = (
            post.get("post_comment_count")
            or post.get("comment_count")
            or post.get("Cc")
            or 0
        )

        post_time = (
            post.get("post_publish_time")
            or post.get("publish_time")
            or post.get("Pt")
            or "未知"
        )
        # 只取日期部分（YYYY-MM-DD）
        if isinstance(post_time, str) and len(post_time) > 10:
            post_time = post_time[:10]

        lines.append(f"{idx}. [{title}]")
        lines.append(f"   阅读: {read_count} | 评论: {comment_count} | 时间: {post_time}")
        lines.append("")

    return "\n".join(lines)
