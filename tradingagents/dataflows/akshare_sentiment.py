"""AKShare-based sentiment data for A-share stocks.

Provides structured sentiment/popularity data from Eastmoney via AKShare,
replacing the defunct Xueqiu and Eastmoney Guba scrapers.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)

try:
    import akshare as ak
except ImportError:
    ak = None
    logger.warning("akshare is not installed. A-share sentiment data will be unavailable.")


# ---------------------------------------------------------------------------
# Helper / Utility Functions
# ---------------------------------------------------------------------------


def _to_akshare_hot_symbol(ticker: str) -> str:
    """将各种 ticker 格式转为 akshare 人气排名需要的格式（如 "SZ000001" / "SH600000"）。

    支持的输入格式:
    - "600000.SH" -> "SH600000"
    - "000001.SZ" -> "SZ000001"
    - "SH600000"  -> "SH600000"（已是正确格式）
    - "600000"    -> "SH600000"（6/9开头默认SH，0/3开头默认SZ）
    - "518880.SH" -> "SH518880"
    """
    ticker = ticker.strip().upper()

    # 格式: 600000.SH / 000001.SZ
    m = re.match(r"^(\d{6})\.(SH|SZ|SS|BJ)$", ticker)
    if m:
        code, exchange = m.group(1), m.group(2)
        # .SS 也是上海
        if exchange == "SS":
            exchange = "SH"
        return f"{exchange}{code}"

    # 格式: SH600000 / SZ000001（已是正确格式）
    m = re.match(r"^(SH|SZ|BJ)(\d{6})$", ticker)
    if m:
        return ticker

    # 格式: 纯 6 位数字
    m = re.match(r"^(\d{6})$", ticker)
    if m:
        code = m.group(1)
        if code[0] in ("6", "9", "5"):
            return f"SH{code}"
        else:
            return f"SZ{code}"

    # 无法识别，尝试提取数字部分并推断交易所
    digits = re.findall(r"\d+", ticker)
    if digits and len(digits[0]) == 6:
        code = digits[0]
        if code[0] in ("6", "9", "5"):
            return f"SH{code}"
        else:
            return f"SZ{code}"

    # Fallback
    return ticker


def _extract_code(ticker: str) -> str:
    """从 ticker 中提取纯 6 位数字代码。

    支持的输入格式:
    - "600000.SH" -> "600000"
    - "SH600000"  -> "600000"
    - "600000"    -> "600000"
    """
    ticker = ticker.strip().upper()

    # 格式: 600000.SH
    m = re.match(r"^(\d{6})\.[A-Z]{2}$", ticker)
    if m:
        return m.group(1)

    # 格式: SH600000
    m = re.match(r"^[A-Z]{2}(\d{6})$", ticker)
    if m:
        return m.group(1)

    # 格式: 纯数字
    m = re.match(r"^(\d{6})$", ticker)
    if m:
        return m.group(1)

    # 尝试提取数字
    digits = re.findall(r"\d+", ticker)
    if digits:
        return digits[0].zfill(6)

    return ticker


# ---------------------------------------------------------------------------
# Public Functions
# ---------------------------------------------------------------------------


def fetch_akshare_stock_comment(ticker: str) -> str:
    """获取千股千评数据，返回格式化纯文本。

    Parameters
    ----------
    ticker : str
        股票代码，支持多种格式（如 600000、600000.SH、SH600000）。

    Returns
    -------
    str
        格式化的千股千评文本。异常时返回占位符字符串。
    """
    if ak is None:
        logger.warning("akshare 未安装，无法获取千股千评数据")
        return f"[AKShare stock comment data unavailable for {ticker}]"

    target_code = _extract_code(ticker)
    logger.info("获取千股千评数据: ticker=%s, code=%s", ticker, target_code)

    try:
        df = ak.stock_comment_em()

        if df is None or df.empty:
            logger.warning("stock_comment_em 返回空数据")
            return f"[AKShare stock comment data unavailable for {ticker}]"

        logger.debug("stock_comment_em 返回 %d 行, 列: %s", len(df), list(df.columns))

        # 查找 Code 列（兼容不同列名）
        code_col = None
        for candidate in ("代码", "Code", "code", "股票代码"):
            if candidate in df.columns:
                code_col = candidate
                break

        if code_col is None:
            # 如果找不到标准列名，尝试第二列（通常是代码）
            if len(df.columns) >= 2:
                code_col = df.columns[1]
            else:
                logger.warning("无法识别 stock_comment_em 的代码列")
                return f"[AKShare stock comment data unavailable for {ticker}]"

        # 标准化 Code 列并筛选
        df["_norm_code"] = df[code_col].apply(lambda x: str(x).strip().zfill(6))
        row = df[df["_norm_code"] == target_code]

        if row.empty:
            logger.info("千股千评中未找到 %s 的数据", target_code)
            return f"[AKShare stock comment data unavailable for {ticker}]"

        row = row.iloc[0]

        # 提取各字段（兼容中英文列名）
        def _get(keys, default="--"):
            for k in keys:
                if k in row.index and pd.notna(row[k]):
                    return row[k]
            return default

        name = _get(["名称", "Name", "股票简称"])
        total_score = _get(["综合得分", "TotalScore", "总分"])
        ranking = _get(["综合排名", "Ranking", "排名"])
        focus = _get(["关注指数", "Focus", "关注度"])
        jgcyd = _get(["机构参与度", "JGCYD"])
        zlcb = _get(["主力成本", "ZLCB", "主力成本(1日)"])
        zlcb20 = _get(["ZLCB20R", "主力成本20日", "主力成本(20日)"])
        zlcb60 = _get(["ZLCB60R", "主力成本60日", "主力成本(60日)"])
        new_price = _get(["最新价", "New", "最新"])
        change_pct = _get(["涨跌幅", "ChangePercent", "涨跌幅(%)"])
        pe = _get(["市盈率", "PERation", "PE"])
        turnover = _get(["换手率", "TurnoverRate", "换手率(%)"])
        tdate = _get(["交易日", "TDate", "日期"])

        # 格式化日期
        if tdate != "--":
            try:
                tdate_str = pd.to_datetime(tdate).strftime("%Y-%m-%d")
            except Exception:
                tdate_str = str(tdate)
        else:
            tdate_str = datetime.now().strftime("%Y-%m-%d")

        # 格式化涨跌幅
        change_str = "--"
        if change_pct != "--":
            try:
                pct_val = float(change_pct)
                change_str = f"+{pct_val:.2f}%" if pct_val >= 0 else f"{pct_val:.2f}%"
            except (ValueError, TypeError):
                change_str = str(change_pct)

        # 生成分析提示
        hint_parts = []
        try:
            if total_score != "--":
                score_val = float(total_score)
                if score_val >= 70:
                    hint_parts.append("综合评分较高")
                elif score_val >= 50:
                    hint_parts.append("综合评分中等")
                else:
                    hint_parts.append("综合评分偏低")
        except (ValueError, TypeError):
            pass

        try:
            if jgcyd != "--":
                jgcyd_val = float(jgcyd)
                if jgcyd_val >= 60:
                    hint_parts.append("机构参与度较高")
                elif jgcyd_val >= 30:
                    hint_parts.append("机构参与度中等")
                else:
                    hint_parts.append("机构参与度偏低")
        except (ValueError, TypeError):
            pass

        try:
            if zlcb != "--" and zlcb60 != "--":
                zlcb_val = float(zlcb)
                zlcb60_val = float(zlcb60)
                hint_parts.append(
                    f"主力成本集中在{zlcb60_val:.2f}-{zlcb_val:.2f}区间"
                )
        except (ValueError, TypeError):
            pass

        hint = "，".join(hint_parts) + "。" if hint_parts else "暂无分析提示。"

        # 构建输出
        lines = [
            f"=== 千股千评数据 ({ticker}) ===",
            f"股票名称: {name}",
            f"数据日期: {tdate_str}",
            "",
            f"综合评分: {total_score}/100 (排名: 第 {ranking} 名)",
            f"关注指数: {focus}",
            f"机构参与度: {jgcyd}%",
            f"主力成本(1日): {zlcb}",
            f"主力成本(20日): {zlcb20}",
            f"主力成本(60日): {zlcb60}",
            "",
            f"最新价: {new_price} | 涨跌幅: {change_str}",
            f"市盈率: {pe} | 换手率: {turnover}%",
            "",
            f"分析提示: {hint}",
        ]

        result = "\n".join(lines)
        logger.debug("千股千评数据获取成功: %s", target_code)
        return result

    except Exception as exc:  # noqa: BLE001
        logger.warning("获取千股千评数据失败 (%s): %s", ticker, exc)
        return f"[AKShare stock comment data unavailable for {ticker}]"


def fetch_akshare_hot_rank(ticker: str) -> str:
    """获取个股人气排名和热度趋势，返回格式化纯文本。

    Parameters
    ----------
    ticker : str
        股票代码，支持多种格式（如 600000、600000.SH、SH600000）。

    Returns
    -------
    str
        格式化的人气排名文本。异常时返回占位符字符串。
    """
    if ak is None:
        logger.warning("akshare 未安装，无法获取人气排名数据")
        return f"[AKShare hot rank data unavailable for {ticker}]"

    symbol = _to_akshare_hot_symbol(ticker)
    logger.info("获取个股人气排名: ticker=%s, symbol=%s", ticker, symbol)

    try:
        # 获取最新排名
        latest_df = ak.stock_hot_rank_latest_em(symbol=symbol)

        if latest_df is None or latest_df.empty:
            logger.warning("stock_hot_rank_latest_em 返回空数据: %s", symbol)
            return f"[AKShare hot rank data unavailable for {ticker}]"

        logger.debug(
            "stock_hot_rank_latest_em 返回 %d 行, 列: %s",
            len(latest_df), list(latest_df.columns),
        )

        # latest_df 通常是 item/value 两列
        latest_dict = {}
        if "item" in latest_df.columns and "value" in latest_df.columns:
            for _, r in latest_df.iterrows():
                latest_dict[str(r["item"])] = r["value"]
        elif len(latest_df.columns) == 2:
            for _, r in latest_df.iterrows():
                latest_dict[str(r.iloc[0])] = r.iloc[1]
        else:
            # 单行 DataFrame
            for col in latest_df.columns:
                latest_dict[col] = latest_df.iloc[0][col]

        # 提取排名信息
        def _find_val(keys, default="--"):
            for k in keys:
                if k in latest_dict:
                    return latest_dict[k]
            return default

        current_rank = _find_val(["当前排名", "排名", "rank", "current_rank"])
        total_stock = _find_val(["总数", "全市场", "total", "market_total"])
        rank_change = _find_val(["排名变化", "rank_change", "变化"])

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 格式化排名变化文字
        rank_change_str = "--"
        if rank_change != "--":
            try:
                change_val = int(float(str(rank_change)))
                if change_val > 0:
                    rank_change_str = f"上升 {change_val} 位"
                elif change_val < 0:
                    rank_change_str = f"下降 {abs(change_val)} 位"
                else:
                    rank_change_str = "持平"
            except (ValueError, TypeError):
                rank_change_str = str(rank_change)

        # 构建基本信息
        if total_stock != "--":
            rank_line = f"当前人气排名: 第 {current_rank} 名 / 全市场 {total_stock} 只"
        else:
            rank_line = f"当前人气排名: 第 {current_rank} 名"

        lines = [
            f"=== 个股人气数据 ({ticker}) ===",
            f"数据时间: {now_str}",
            "",
            rank_line,
            f"排名变化: {rank_change_str}",
        ]

        # 尝试获取历史趋势
        detail_lines = []
        trend_analysis = ""
        try:
            detail_df = ak.stock_hot_rank_detail_em(symbol=symbol)

            if detail_df is not None and not detail_df.empty:
                logger.debug(
                    "stock_hot_rank_detail_em 返回 %d 行, 列: %s",
                    len(detail_df), list(detail_df.columns),
                )

                # 列: 时间, 排名, 证券代码, 新晋粉丝, 铁杆粉丝
                time_col = None
                for c in ("时间", "time", "日期"):
                    if c in detail_df.columns:
                        time_col = c
                        break

                rank_col = None
                for c in ("排名", "rank"):
                    if c in detail_df.columns:
                        rank_col = c
                        break

                new_fan_col = None
                for c in ("新晋粉丝", "new_fans", "新晋粉丝占比"):
                    if c in detail_df.columns:
                        new_fan_col = c
                        break

                old_fan_col = None
                for c in ("铁杆粉丝", "old_fans", "铁杆粉丝占比"):
                    if c in detail_df.columns:
                        old_fan_col = c
                        break

                # 取最近 7 天的数据
                detail_df = detail_df.tail(7).reset_index(drop=True)

                # 按时间倒序显示（最新在上）
                detail_df_display = detail_df.iloc[::-1].reset_index(drop=True)

                for _, r in detail_df_display.iterrows():
                    date_str = "--"
                    if time_col:
                        try:
                            date_str = pd.to_datetime(r[time_col]).strftime("%m-%d")
                        except Exception:
                            date_str = str(r[time_col])[:5]

                    r_rank = r[rank_col] if rank_col and pd.notna(r.get(rank_col)) else "--"

                    new_fan_pct = "--"
                    if new_fan_col and pd.notna(r.get(new_fan_col)):
                        try:
                            val = float(r[new_fan_col])
                            # 如果是0-1区间则转百分比，如果已是百分比则直接用
                            new_fan_pct = f"{val * 100:.0f}%" if val <= 1 else f"{val:.0f}%"
                        except (ValueError, TypeError):
                            new_fan_pct = str(r[new_fan_col])

                    old_fan_pct = "--"
                    if old_fan_col and pd.notna(r.get(old_fan_col)):
                        try:
                            val = float(r[old_fan_col])
                            old_fan_pct = f"{val * 100:.0f}%" if val <= 1 else f"{val:.0f}%"
                        except (ValueError, TypeError):
                            old_fan_pct = str(r[old_fan_col])

                    detail_lines.append(
                        f"{date_str}: 排名 {r_rank} | 新晋粉丝 {new_fan_pct} | 铁杆粉丝 {old_fan_pct}"
                    )

                # 生成趋势分析
                if rank_col and len(detail_df) >= 2:
                    try:
                        first_rank = int(float(detail_df.iloc[0][rank_col]))
                        last_rank = int(float(detail_df.iloc[-1][rank_col]))
                        rank_diff = first_rank - last_rank

                        if rank_diff > 0:
                            trend_direction = f"排名从{first_rank}上升至{last_rank}"
                        elif rank_diff < 0:
                            trend_direction = f"排名从{first_rank}下降至{last_rank}"
                        else:
                            trend_direction = f"排名稳定在{last_rank}"

                        # 粉丝变化分析
                        fan_hint = ""
                        if old_fan_col:
                            try:
                                first_old = float(detail_df.iloc[0][old_fan_col])
                                last_old = float(detail_df.iloc[-1][old_fan_col])
                                if first_old <= 1:
                                    first_old *= 100
                                    last_old *= 100
                                if last_old > first_old:
                                    fan_hint = (
                                        f"，铁杆粉丝占比上升({first_old:.0f}%→{last_old:.0f}%)，"
                                        f"表明市场关注度持续增加且粉丝粘性增强"
                                    )
                                elif last_old < first_old:
                                    fan_hint = (
                                        f"，铁杆粉丝占比下降({first_old:.0f}%→{last_old:.0f}%)，"
                                        f"新关注者增多但粘性有所减弱"
                                    )
                            except (ValueError, TypeError):
                                pass

                        trend_analysis = f"近7天{trend_direction}{fan_hint}。"
                    except (ValueError, TypeError):
                        trend_analysis = "趋势数据解析异常。"
                else:
                    trend_analysis = "趋势数据不足，无法分析。"
            else:
                detail_lines = []
                trend_analysis = "暂无历史趋势数据。"

        except Exception as detail_exc:  # noqa: BLE001
            logger.debug("获取人气排名历史趋势失败 (%s): %s", symbol, detail_exc)
            detail_lines = []
            trend_analysis = "暂无历史趋势数据。"

        # 组装完整输出
        if detail_lines:
            lines.append("")
            lines.append("--- 近 7 天热度趋势 ---")
            lines.extend(detail_lines)

        lines.append("")
        lines.append(f"趋势分析: {trend_analysis}")

        result = "\n".join(lines)
        logger.debug("人气排名数据获取成功: %s", symbol)
        return result

    except Exception as exc:  # noqa: BLE001
        logger.warning("获取人气排名数据失败 (%s): %s", ticker, exc)
        return f"[AKShare hot rank data unavailable for {ticker}]"
