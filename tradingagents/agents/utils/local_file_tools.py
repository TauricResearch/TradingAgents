"""
本地文件信息工具
扫描 TRADINGAGENTS_LOCAL_FILES_DIR（来自 .env）目录，
根据股票代码或公司名称匹配文件名，读取文件内容作为信息源。
支持格式：.txt、.md、.docx、.pdf
"""

import os
import re
from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool


# --------------------------------------------------------------------------- #
#  文件名相关性匹配
# --------------------------------------------------------------------------- #

# 常见股票代码 → 公司关键词映射（可按需扩展）
_TICKER_ALIASES: dict[str, list[str]] = {
    "AAPL":  ["apple", "苹果"],
    "MSFT":  ["microsoft", "微软"],
    "GOOGL": ["google", "alphabet", "谷歌"],
    "GOOG":  ["google", "alphabet", "谷歌"],
    "AMZN":  ["amazon", "亚马逊"],
    "TSLA":  ["tesla", "特斯拉"],
    "META":  ["meta", "facebook", "脸书"],
    "NVDA":  ["nvidia", "英伟达"],
    "INTC":  ["intel", "英特尔"],
    "AMD":   ["amd", "advanced micro", "超威半导体"],
    "BABA":  ["alibaba", "阿里巴巴", "阿里"],
    "JD":    ["jd", "京东"],
    "PDD":   ["pdd", "temu", "拼多多"],
    "BIDU":  ["baidu", "百度"],
    "NIO":   ["nio", "蔚来"],
    "LI":    ["li auto", "理想汽车", "理想"],
    "XPEV":  ["xpeng", "小鹏汽车", "小鹏"],
    "BYD":   ["byd", "比亚迪"],
    "600519":["moutai", "茅台", "贵州茅台"],
    "000858":["wuliangye", "五粮液"],
}


def _get_company_keywords(ticker: str) -> list[str]:
    """返回该 ticker 对应的所有关键词（ticker 本身 + 已知别名）。

    针对含交易所后缀的 ticker（如 03317.HK、600519.SS、0700.HK），
    额外把点前面的纯代码部分单独加入，方便匹配用户命名为
    "03317纪要.md"、"600519调研.docx" 这类文件。
    同时也加入连字符/下划线替代点的变体（03317-hk、03317_hk）。
    """
    ticker_upper = ticker.upper()
    keywords = [ticker_upper, ticker.lower()]

    # 处理含交易所后缀的 ticker，如 "03317.HK"、"600519.SS"
    if "." in ticker:
        code_part, suffix_part = ticker.rsplit(".", 1)  # 只在最后一个点处分割
        keywords.append(code_part.upper())
        keywords.append(code_part.lower())
        # 连字符/下划线变体：03317-hk、03317_hk
        keywords.append(f"{code_part.lower()}-{suffix_part.lower()}")
        keywords.append(f"{code_part.lower()}_{suffix_part.lower()}")

        # 用点前的代码查静态映射表（如 "600519" → 茅台）
        if code_part.upper() in _TICKER_ALIASES:
            keywords.extend(_TICKER_ALIASES[code_part.upper()])

    # 先查静态映射表（完整 ticker）
    if ticker_upper in _TICKER_ALIASES:
        keywords.extend(_TICKER_ALIASES[ticker_upper])

    # 再用 yfinance 动态获取公司全名（失败时静默跳过）
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        long_name = info.get("longName", "")
        short_name = info.get("shortName", "")
        for name in [long_name, short_name]:
            if name:
                # 将公司全名拆词，过滤掉过短或通用词
                words = re.split(r"[\s,.\-]+", name)
                for w in words:
                    w = w.strip()
                    if len(w) >= 3 and w.lower() not in {
                        "inc", "corp", "ltd", "llc", "co", "the", "and",
                        "group", "holdings", "technologies", "technology",
                    }:
                        keywords.append(w.lower())
    except Exception:
        pass

    # 去重并过滤空串
    seen = set()
    unique = []
    for k in keywords:
        kl = k.lower().strip()
        if kl and kl not in seen:
            seen.add(kl)
            unique.append(kl)
    return unique


def _filename_matches(filename: str, keywords: list[str]) -> bool:
    """文件名（不含扩展名）是否包含任意关键词（大小写不敏感）。"""
    stem = Path(filename).stem.lower()
    return any(kw in stem for kw in keywords)


# --------------------------------------------------------------------------- #
#  文件内容读取
# --------------------------------------------------------------------------- #

def _read_txt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"[读取失败: {e}]"


def _read_docx(path: Path) -> str:
    try:
        import docx  # python-docx
        doc = docx.Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except ImportError:
        return "[读取 .docx 失败：请安装 python-docx（pip install python-docx）]"
    except Exception as e:
        return f"[读取 .docx 失败: {e}]"


def _read_pdf(path: Path) -> str:
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
        return "\n".join(pages)
    except ImportError:
        pass  # 回退到 PyPDF2
    try:
        import PyPDF2
        text_parts = []
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text_parts.append(page.extract_text() or "")
        return "\n".join(text_parts)
    except ImportError:
        return "[读取 .pdf 失败：请安装 pdfplumber（pip install pdfplumber）]"
    except Exception as e:
        return f"[读取 .pdf 失败: {e}]"


def _read_file(path: Path) -> str:
    """根据扩展名分发读取逻辑，返回文件文本内容。"""
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".rst", ".csv"}:
        return _read_txt(path)
    elif suffix == ".docx":
        return _read_docx(path)
    elif suffix == ".pdf":
        return _read_pdf(path)
    else:
        # 尝试当作纯文本读取
        return _read_txt(path)


# --------------------------------------------------------------------------- #
#  LangChain Tool
# --------------------------------------------------------------------------- #

@tool
def get_local_file_info(
    ticker: Annotated[str, "股票代码，例如 NVDA、INTC、600519"],
) -> str:
    """
    在本地文件夹中搜索与指定股票相关的文件（交流纪要、研报、内部文档等），
    并返回匹配文件的全部内容。
    文件夹路径由环境变量 TRADINGAGENTS_LOCAL_FILES_DIR 指定。
    文件名包含股票代码或公司名称（中英文）时视为匹配。
    支持 .txt / .md / .docx / .pdf 格式。
    """
    local_dir = os.environ.get("TRADINGAGENTS_LOCAL_FILES_DIR", "").strip()
    if not local_dir:
        return "未配置本地文件目录（请在 .env 中设置 TRADINGAGENTS_LOCAL_FILES_DIR）。"

    dir_path = Path(local_dir)
    if not dir_path.exists():
        return f"本地文件目录不存在：{local_dir}"

    keywords = _get_company_keywords(ticker)
    supported_suffixes = {".txt", ".md", ".rst", ".docx", ".pdf", ".csv"}

    matched_files: list[tuple[Path, str]] = []  # (文件路径, 来源描述)

    for entry in sorted(dir_path.iterdir()):
        if entry.is_file():
            # 根目录下的散文件：用文件名匹配
            if entry.suffix.lower() in supported_suffixes and _filename_matches(entry.name, keywords):
                matched_files.append((entry, ""))
        elif entry.is_dir():
            # 子文件夹：用文件夹名匹配，匹配上则读取文件夹内所有支持格式的文件
            if _filename_matches(entry.name, keywords):
                for f in sorted(entry.iterdir()):
                    if f.is_file() and f.suffix.lower() in supported_suffixes:
                        matched_files.append((f, entry.name))

    if not matched_files:
        kw_display = "、".join(keywords[:8])
        return (
            f"在 {local_dir} 中未找到与 {ticker} 相关的本地文件。\n"
            f"（已搜索关键词：{kw_display}）"
        )

    results = []
    for f, folder in matched_files:
        content = _read_file(f)
        # 内容截断，避免超出 context 限制（单文件最多 8000 字）
        if len(content) > 8000:
            content = content[:8000] + f"\n\n[... 内容已截断，原文件共约 {len(content)} 字 ...]"
        # 标题里标注来源，方便 LLM 区分不同文件
        source = f"{folder}/{f.name}" if folder else f.name
        results.append(f"=== 文件：{source} ===\n{content}")

    header = f"找到 {len(matched_files)} 个与 {ticker} 相关的本地文件：\n\n"
    return header + "\n\n".join(results)
