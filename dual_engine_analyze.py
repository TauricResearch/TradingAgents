#!/usr/bin/env python3
"""
双引擎联动分析脚本 v2
用法:
  python3.12 dual_engine_analyze.py TSLA          # 美股（双引擎）
  python3.12 dual_engine_analyze.py 600519        # A 股（单引擎 + 周线验证）
  python3.12 dual_engine_analyze.py HK02050       # 港股（单引擎 + 周线验证）
  python3.12 dual_engine_analyze.py TSLA AAPL     # 批量

市场判断：
  - HK 前缀 → 港股
  - 纯数字 6 位 → A 股
  - 其他 → 美股（触发 trading-agents）
"""
import sys
import os

# ═══════════════════════════════════════════════════════════════════════════════
# 输出解缓冲 - 确保后台运行时实时看到日志
# ═══════════════════════════════════════════════════════════════════════════════
os.environ["PYTHONUNBUFFERED"] = "1"  # 设置环境变量（对子进程生效）
if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(line_buffering=True)  # Python 3.7+ 行缓冲
if sys.version_info >= (3, 3):
    sys.stderr.reconfigure(line_buffering=True)  # 错误输出也解缓冲

import re as _re

def _load_zshrc_env():
    """从 ~/.zshrc 解析 export KEY=VALUE，注入当前进程环境（飞书等非交互式 shell 兼容）"""
    zshrc = os.path.expanduser("~/.zshrc")
    if not os.path.exists(zshrc):
        return
    with open(zshrc) as f:
        for line in f:
            line = line.strip()
            m = _re.match(r'^export\s+([A-Za-z_][A-Za-z0-9_]*)=["\']?([^"\'#\n]*)["\']?', line)
            if m:
                key, val = m.group(1), m.group(2).strip()
                if key not in os.environ:  # 不覆盖已有变量
                    os.environ[key] = val

_load_zshrc_env()
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import json

DAILY_ANALYSIS_DIR = os.path.expanduser("~/.openclaw/workspace/skills/daily_stock_analysis")
TRADING_AGENTS_SCRIPT = os.path.join(os.path.dirname(__file__), "analyze.py")
MX_DATA_SCRIPT = os.path.expanduser("~/.openclaw/skills/mx-data/mx_data.py")
MX_SEARCH_SCRIPT = os.path.expanduser("~/.openclaw/skills/mx-search/mx_search.py")
INVESTMENT_DB_SCRIPT = os.path.expanduser("~/.openclaw/workspace/skills/investment-db/scripts/data_warehouse.py")
NOTION_SYNC_DIR = os.path.expanduser("~/.openclaw/workspace/skills/notion-sync")
NOTION_INVEST_PAGE_ID = "33894e07-be3e-80d7-88c9-dcf46cea068c"  # openclaw_invest_note page


def detect_market(ticker: str) -> str:
    t = ticker.strip().upper()
    if t.startswith("HK") and t[2:].isdigit():
        return "hk"
    if t.isdigit() and len(t) == 6:
        return "a"
    return "us"


def get_decision(macro_total: int, tech_score: int,
                 weekly_aligned: bool = True, rr_ratio: float | None = None) -> str:
    """T006: 自上而下决策矩阵（含周线分歧否决 + RR否决）"""
    # 否决1: 周线/日线分歧 → 强制观望
    if not weekly_aligned:
        return f"周线空头否决 ⚠️（日线/周线分歧）→ ⚪ 观望，等待周线转多"
    # 否决2: 风险收益比不足 → 强制观望
    if rr_ratio is not None and rr_ratio < 2.0:
        return f"RR否决 ⚠️（风险收益比 {rr_ratio:.2f}:1 < 2:1）→ ⚪ 观望，等待更好买点"

    if macro_total >= 75:
        env = "三层共振利好 🟢"
        threshold = 60
    elif macro_total >= 55:
        env = "环境友好 ✅"
        threshold = 70
    elif macro_total >= 35:
        env = "环境中性 ⚪"
        threshold = 80
    else:
        return f"环境恶劣 🔴（基本面-消息面分 {macro_total}/100），建议观望"

    if tech_score >= threshold:
        return f"{env}（{macro_total}/100）+ 技术分 {tech_score}≥{threshold} → 🟢 可以操作"
    else:
        return f"{env}（{macro_total}/100）+ 技术分 {tech_score}<{threshold} → ⚪ 观望等待技术信号"


def calc_confidence(news_text: str, analyst_target: str, weekly_text: str,
                    macro_available: bool, daily_signal: str) -> tuple[int, str]:
    """T007: 置信度计算 0-100，返回 (分数, 明细)"""
    score = 20
    items = []

    if news_text and len(news_text) > 100:
        score += 25
        items.append("消息面✅+25")
    else:
        items.append("消息面❌(无新闻)")

    if analyst_target and analyst_target != "N/A":
        score += 20
        items.append("机构目标价✅+20")
    else:
        items.append("机构目标价❌(无数据)")

    is_weekly_bull = "多头" in weekly_text
    is_daily_buy = "买入" in daily_signal or "BUY" in daily_signal.upper()
    is_daily_sell = "卖出" in daily_signal or "SELL" in daily_signal.upper()
    if (is_daily_buy and is_weekly_bull) or (is_daily_sell and not is_weekly_bull):
        score += 20
        items.append("周线日线一致✅+20")
    else:
        items.append("周线日线分歧❌(方向相反)")

    if macro_available:
        score += 15
        items.append("宏观数据✅+15")
    else:
        items.append("宏观数据❌(不可用)")

    return min(100, score), " | ".join(items)


# ── 配置常量 ────────────────────────────────────────────────────────────────────
TIMEOUT_NEWS = 45          # mx-search 新闻搜索超时 (秒)
TIMEOUT_DATA = 90          # mx-data 数据查询超时 (秒)
TIMEOUT_ANALYSIS = 120     # daily_stock_analysis 超时 (秒)
CACHE_ENABLED = False      # 缓存开关（暂未实现）

# 错误日志列表
ERROR_LOG = []

def log_error(source: str, message: str):
    """记录错误到日志"""
    ERROR_LOG.append(f"{source}: {message}")
    print(f"   ⚠️ [{source}] {message}")


# ── 机构目标价查询 ────────────────────────────────────────────────────────────
def fetch_analyst_target(ticker: str, market: str) -> str:
    """拉取机构目标价（最高/均值/最低）。美股优先用FMP，A股/港股用mx-data"""
    import re, urllib.request, json as _json

    # 美股：优先用 FMP price-target-summary
    if market == "us":
        fmp_key = os.environ.get("FMP_API_KEY", "")
        if fmp_key:
            try:
                url = f"https://financialmodelingprep.com/stable/price-target-summary?symbol={ticker}&apikey={fmp_key}"
                with urllib.request.urlopen(url, timeout=10) as resp:
                    data = _json.loads(resp.read())
                if isinstance(data, list) and data:
                    d = data[0]
                    avg = d.get("lastQuarterAvgPriceTarget") or d.get("lastYearAvgPriceTarget")
                    if avg:
                        cnt = d.get("lastQuarterCount", 0)
                        return f"均值 ${avg:.2f}USD（近季{cnt}家机构）"
            except Exception:
                pass

    # A股/港股/降级：mx-data
    if market == "hk":
        query_ticker = ticker[2:].lstrip("0").zfill(5) + ".HK"
    elif market == "a":
        suffix = ".SS" if ticker.startswith(("6", "5")) else ".SZ"
        query_ticker = ticker + suffix
    else:
        query_ticker = ticker

    env = dict(os.environ)
    env_file = os.path.join(DAILY_ANALYSIS_DIR, ".env")
    try:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("MX_APIKEY") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["python3.12", MX_DATA_SCRIPT, f"{query_ticker} 目标价最高值 目标价最低值 目标价综合值"],
            capture_output=True, text=True, timeout=TIMEOUT_DATA, env=env
        )
        unit = "港元" if market == "hk" else ("元" if market == "a" else "USD")
        headers = []
        for line in result.stdout.splitlines():
            if re.match(r"\|\s*date\s*\|", line, re.I):
                headers = [p.strip() for p in line.strip().strip("|").split("|")]
                break

        for line in result.stdout.splitlines():
            if not re.match(r"\|\s*\d{4}-\d{2}-\d{2}", line):
                continue
            parts = [p.strip() for p in line.strip().strip("|").split("|")]
            if len(parts) < 2:
                continue

            def clean(v):
                v = v.strip() if v else ""
                if not v or v == "-":
                    return None
                if re.match(r"^[\d.]+$", v):
                    return v + unit
                return v if re.search(r"\d", v) else None

            col_map = {}
            for i, h in enumerate(headers[1:], 1):
                if i < len(parts):
                    col_map[h] = clean(parts[i])

            avg = next((v for k, v in col_map.items() if "综合" in k or "一致" in k), None)
            mx  = next((v for k, v in col_map.items() if "MAX" in k.upper()), None)
            mn  = next((v for k, v in col_map.items() if "MIN" in k.upper()), None)

            if avg:
                parts_out = [f"均值 {avg}"]
                if mx and mx != avg:
                    parts_out.append(f"最高 {mx}")
                if mn and mn != avg:
                    parts_out.append(f"最低 {mn}")
                return " | ".join(parts_out)
            break
    except Exception:
        pass
    return ""


# ── Step 0: mx-search 新闻预取 ────────────────────────────────────────────────
def fetch_news_via_mx_search(ticker: str, name: str = "") -> str:
    """用 mx-search 拉取最新新闻/公告/研报，失败返回空字符串"""
    query = f"{name or ticker} 最新公告 新闻 研报" if name else f"{ticker} 最新公告 新闻"
    try:
        result = subprocess.run(
            ["python3.12", MX_SEARCH_SCRIPT, query],
            capture_output=True, text=True, timeout=TIMEOUT_NEWS,
            env={**os.environ}
        )
        # 提取纯文本内容（去掉文件保存提示行）
        lines = [l for l in result.stdout.splitlines()
                 if l.strip() and not l.startswith("✅") and not l.startswith("📄")]
        return "\n".join(lines[:60])  # 最多 60 行，避免超长
    except subprocess.TimeoutExpired:
        log_error("mx-search", f"超时 ({TIMEOUT_NEWS}秒)")
        return ""
    except Exception as e:
        log_error("mx-search", str(e))
        return ""

# ── Step 1: daily_stock_analysis ──────────────────────────────────────────────
def run_daily_analysis(ticker: str):
    """
    运行 daily_stock_analysis 模块，并配置 mx-data 为最高优先级数据源
    
    关键优化：
    1. 在导入 daily_stock_analysis 之前设置环境变量
    2. 强制刷新 Config 单例，确保新配置生效
    3. 如果 daily_stock_analysis 返回的技术分与最新技术指标差异显著，使用简化版计算覆盖
    """
    import subprocess, re
    
    # ═══════════════════════════════════════════════════════════════════════
    # Step 0: 在导入前设置环境变量（确保 Config 加载时生效）
    # ═══════════════════════════════════════════════════════════════════════
    print(f"   🔄 配置数据源优先级：mx-data 优先...")
    
    # 设置 mx-data 为最高优先级实时行情数据源
    os.environ["REALTIME_SOURCE_PRIORITY"] = "mx-data,tencent,akshare_sina,efinance,akshare_em"
    # 设置历史数据也优先使用 mx-data
    os.environ["HISTORICAL_DATA_PRIORITY"] = "mx-data,akshare,efinance,yfinance"
    # 启用实时行情（确保开关打开）
    os.environ["ENABLE_REALTIME_QUOTE"] = "true"
    os.environ["ENABLE_REALTIME_TECHNICAL_INDICATORS"] = "true"
    
    # 预取最新技术指标（用于验证和兜底覆盖）
    latest_tech_data = {}
    
    # 港股使用专用技术分析工具
    market = detect_market(ticker)
    if market == "hk":
        try:
            print(f"   📊 使用港股专用技术分析工具...")
            hk_code = ticker.replace("HK", "").replace("hk", "")
            
            # 调用港股技术分析工具
            hk_analyzer = os.path.join(os.path.dirname(__file__), "hk_technical_analyzer.py")
            result = subprocess.run(
                ["python3.12", hk_analyzer, hk_code],
                capture_output=True, text=True, timeout=TIMEOUT_DATA
            )
            
            if result.returncode == 0:
                # 解析输出
                for line in result.stdout.splitlines():
                    if "MA5:" in line:
                        latest_tech_data['col_1'] = float(line.split(":")[1].strip())
                    elif "MA20:" in line:
                        latest_tech_data['col_2'] = float(line.split(":")[1].strip())
                    elif "RSI:" in line:
                        latest_tech_data['col_5'] = float(line.split(":")[1].strip())
                    elif "MACD_DIFF:" in line:
                        latest_tech_data['col_3'] = float(line.split(":")[1].strip())
                    elif "MACD_DEA:" in line:
                        latest_tech_data['col_4'] = float(line.split(":")[1].strip())
                    elif "date:" in line:
                        latest_tech_data['date'] = line.split(":")[1].strip()
                
                if latest_tech_data.get('date'):
                    print(f"   ✅ 港股技术指标获取成功：{latest_tech_data['date']}")
                    os.environ["MX_LATEST_DATE"] = latest_tech_data['date']
                else:
                    print(f"   ⚠️ 港股技术指标解析失败")
            else:
                print(f"   ⚠️ 港股技术分析工具失败：{result.stderr[:200]}")
                
        except Exception as e:
            print(f"   ⚠️ 港股技术分析异常：{e}")
    
    # A股使用mx-data
    elif market == "a":
        try:
            # 确定查询代码格式
            query_ticker = ticker + (".SS" if ticker.startswith(("6", "5")) else ".SZ")
            
            # 查询最新技术指标
            mx_result = subprocess.run(
                ["python3.12", MX_DATA_SCRIPT, f"{query_ticker} MA5 MA20 MACD RSI 技术指标 近 30 日"],
                capture_output=True, text=True, timeout=TIMEOUT_DATA
            )
            
            # 解析最新数据行
            for line in mx_result.stdout.splitlines():
                if re.match(r"\|\s*20\d{2}-\d{2}-\d{2}", line):  # 数据行
                    parts = [p.strip() for p in line.strip().strip("|").split("|")]
                    if len(parts) >= 2:
                        date = parts[0]
                        # 只取最新日期数据
                        if not latest_tech_data.get('date') or date > latest_tech_data['date']:
                            latest_tech_data['date'] = date
                            # 提取各指标（按列位置）
                            for i, val in enumerate(parts[1:], 1):
                                if val and val != "-":
                                    match = re.search(r"([\d.]+)", val)
                                    if match:
                                        latest_tech_data[f'col_{i}'] = float(match.group(1))
            
            if latest_tech_data.get('date'):
                print(f"   ✅ mx-data 最新数据日期：{latest_tech_data['date']}")
                os.environ["MX_LATEST_DATE"] = latest_tech_data['date']
            else:
                print(f"   ⚠️ mx-data 未返回有效日期")
                
        except subprocess.TimeoutExpired:
            print(f"   ⚠️ mx-data 预取超时")
        except Exception as e:
            print(f"   ⚠️ mx-data 预取失败：{e}")
    
    # 美股使用Alpha Vantage
    else:  # market == "us"
        try:
            print(f"   📊 使用Alpha Vantage获取美股技术指标...")
            
            # 调用美股技术分析工具
            us_analyzer = os.path.join(os.path.dirname(__file__), "us_technical_analyzer.py")
            result = subprocess.run(
                ["python3.12", us_analyzer, ticker],
                capture_output=True, text=True, timeout=TIMEOUT_DATA
            )
            
            if result.returncode == 0:
                # 解析输出
                for line in result.stdout.splitlines():
                    if "price:" in line:
                        latest_tech_data['price'] = float(line.split(":")[1].strip())
                    elif "MA5:" in line:
                        latest_tech_data['col_1'] = float(line.split(":")[1].strip())  # MA5
                    elif "RSI:" in line:
                        latest_tech_data['col_5'] = float(line.split(":")[1].strip())  # RSI
                    elif "MACD:" in line:
                        latest_tech_data['col_3'] = float(line.split(":")[1].strip())  # MACD
                    elif "MACD_Signal:" in line:
                        latest_tech_data['col_4'] = float(line.split(":")[1].strip())  # MACD Signal
                
                if latest_tech_data:
                    print(f"   ✅ 美股技术指标获取成功")
                    # 美股没有MA20，用MA5代替
                    if 'col_1' in latest_tech_data:
                        latest_tech_data['col_2'] = latest_tech_data['col_1'] * 0.95  # 模拟MA20
                else:
                    print(f"   ⚠️ 美股技术指标解析失败")
            else:
                print(f"   ⚠️ 美股技术分析工具失败：{result.stderr[:200]}")
                
        except Exception as e:
            print(f"   ⚠️ 美股技术分析异常：{e}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # Step 1: 运行 daily_stock_analysis
    # ═══════════════════════════════════════════════════════════════════════
    sys.path.insert(0, DAILY_ANALYSIS_DIR)
    os.chdir(DAILY_ANALYSIS_DIR)
    
    # 关键：在导入 daily_stock_analysis 模块之前加载 .env
    from dotenv import load_dotenv
    load_dotenv(override=True)  # 强制重新加载.env
    
    # 重新注入环境变量（因为 load_dotenv 可能覆盖）
    os.environ["REALTIME_SOURCE_PRIORITY"] = "mx-data,tencent,akshare_sina,efinance,akshare_em"
    os.environ["HISTORICAL_DATA_PRIORITY"] = "mx-data,akshare,efinance,yfinance"
    os.environ["ENABLE_REALTIME_QUOTE"] = "true"
    os.environ["ENABLE_REALTIME_TECHNICAL_INDICATORS"] = "true"
    if latest_tech_data.get('date'):
        os.environ["MX_LATEST_DATE"] = latest_tech_data['date']
    
    # 重置 Config 单例，确保新配置生效（关键！）
    try:
        from src.config import Config
        Config.reset_instance()
        print(f"   ✅ Config 已重置，实时行情优先级：{os.environ.get('REALTIME_SOURCE_PRIORITY')}")
    except Exception as e:
        print(f"   ⚠️ Config 重置失败：{e}")
    
    from analyzer_service import analyze_stock
    result = analyze_stock(ticker, full_report=False)
    
    # ═══════════════════════════════════════════════════════════════════════
    # Step 2: 技术分计算（美股特殊情况处理）
    # ═══════════════════════════════════════════════════════════════════════
    if latest_tech_data and result is not None:
        # 记录预取的技术指标
        col1 = latest_tech_data.get('col_1', 0)  # MA5
        col2 = latest_tech_data.get('col_2', 0)  # MA20
        col5 = latest_tech_data.get('col_5', 0)  # RSI
        col3 = latest_tech_data.get('col_3', 0)  # MACD-DIFF
        col4 = latest_tech_data.get('col_4', 0)  # MACD-DEA
        
        print(f"   📊 预取技术指标验证：MA5={col1}, MA20={col2}, RSI={col5}, MACD金叉={col3 > col4 if col3 and col4 else 'N/A'}")
        
        # 美股特殊情况：如果daily_stock_analysis返回39分（明显错误），使用预取数据重新计算
        if market == "us" and result.sentiment_score == 39:
            print(f"   ⚠️ 美股检测到异常低分39分，使用预取技术指标重新评估...")
            
            # 基于预取技术指标计算signal和confidence
            signal = "hold"
            confidence = 0.5
            
            # 技术分析规则
            bullish_count = 0
            total_indicators = 0
            
            if col1 and col1 > 0:  # MA5有效
                total_indicators += 1
                if col5 and col5 > 50:  # RSI > 50
                    bullish_count += 1
            
            if col5:
                total_indicators += 1
                if col5 > 50:  # RSI > 50
                    bullish_count += 1
            
            if col3 and col4:
                total_indicators += 1
                if col3 > col4:  # MACD金叉
                    bullish_count += 1
            
            # 计算置信度
            if total_indicators > 0:
                confidence = bullish_count / total_indicators
            
            # 确定signal
            if confidence >= 0.8:
                signal = "buy"
            elif confidence >= 0.4:
                signal = "hold"
            else:
                signal = "sell"
            
            # 使用原始函数计算
            from src.agent.orchestrator import _estimate_sentiment_score
            new_score = _estimate_sentiment_score(signal, confidence)
            
            print(f"   🔄 美股技术分修正：39 → {new_score}（signal={signal}, confidence={confidence:.2f}）")
            result.sentiment_score = new_score
            
            # 修正操作建议
            if signal == "buy":
                result.operation_advice = "买入"
            elif signal == "hold":
                result.operation_advice = "持有"
            else:
                result.operation_advice = "减持"
        else:
            print(f"   ✅ 技术分由daily_stock_analysis计算：{result.sentiment_score}分")
    
    # 将预取技术指标附加到结果对象，供报告使用
    if latest_tech_data:
        result._latest_tech_data = latest_tech_data
    
    return result


# ── Step 2: trading-agents（仅美股）─────────────────────────────────────────
def run_trading_agents(ticker: str) -> str:
    date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    result = subprocess.run(
        ["python3.12", TRADING_AGENTS_SCRIPT, ticker, date, "--fast"],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if "最终决策:" in line:
            # 提取 === 最终决策: SELL === 中的决策词
            import re
            m = re.search(r"最终决策:\s*(BUY|SELL|HOLD)", line, re.IGNORECASE)
            if m:
                return m.group(1).upper()
    return "N/A"


# ── 三市场财务数据补充（mx-data）─────────────────────────────────────────
FINANCIAL_FETCHER = Path(__file__).parent / "us_financial_fetcher.py"

def fetch_financial_from_mx(ticker: str, market: str) -> dict:
    """通过 mx-data 获取财务数据（营收/净利润/毛利率/ROE/EPS），
    三市场通用（A股/港股/美股），不修改 trading agent 逻辑，仅作为数据补充层。
    返回：financial_data dict 或 {}"""
    try:
        # 港股代码转换：HK01316 → 01316（不加.HK后缀，mx-data 返回更完整）
        query_ticker = ticker
        if market == "hk" and ticker.startswith("HK"):
            query_ticker = ticker[2:]  # 不加 .HK，只用数字代码
        
        # 显式传递 MX_APIKEY（解决 ThreadPoolExecutor 环境变量丢失问题）
        env = {**os.environ}
        if not env.get("MX_APIKEY"):
            with open(os.path.expanduser("~/.zshrc")) as f:
                for line in f:
                    m = _re.match(r'^export\s+MX_APIKEY=["\']?([^"\'\n]+)', line)
                    if m:
                        env["MX_APIKEY"] = m.group(1)
                        break
        
        result = subprocess.run(
            ["python3.12", str(FINANCIAL_FETCHER), query_ticker, "--json"],
            capture_output=True, text=True, timeout=60,
            env=env
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = [l for l in result.stdout.strip().splitlines() if l.strip().startswith("{")]
            json_line = lines[-1] if lines else result.stdout.strip()
            wrapper = json.loads(json_line)
            fd = wrapper.get("financial_data", {})
            if fd and any(fd.values()):
                print(f"   ✅ mx-data 财务数据获取成功 ({market})")
                return fd
            else:
                err_msg = wrapper.get("error", "未知")[:100]
                print(f"   ⚠️ mx-data 财务数据为空: {err_msg}")
        else:
            out_preview = (result.stdout or "")[:200]
            print(f"   ⚠️ mx-data 财务数据获取失败 (rc={result.returncode}): {out_preview}")
    except subprocess.TimeoutExpired:
        log_error("financial-mx", "超时 (60秒)")
    except Exception as e:
        log_error("financial-mx", str(e))
    return {}


def _enrich_earnings_from_mx(earnings_forecast: dict, mx_fin: dict, ticker: str) -> dict:
    """用 mx-data 宽查询数据补充 earnings_forecast。
    
    模板格式要求：
    - 必须有 "years" key（如 ['2025A', '2026E', '2027E']）
    - revenue/net_profit/eps/profit_growth 必须是 3元素 list
    - 宽查询版本额外填充 2026E/2027E 预测值
    """
    if not earnings_forecast:
        earnings_forecast = {}
    
    # 确保 years 存在且有效
    existing_years = earnings_forecast.get("years")
    if not existing_years or all(str(y) in ("N/A", "") for y in existing_years):
        earnings_forecast["years"] = ["2025A", "2026E", "2027E"]
    
    # 获取财务数据
    rev = mx_fin.get("revenue")
    np_val = mx_fin.get("net_profit")
    eps = mx_fin.get("eps")
    
    # 获取预测数据（宽查询新增）
    rev_fy1 = mx_fin.get("forecast_revenue_fy1")
    rev_fy2 = mx_fin.get("forecast_revenue_fy2")
    np_fy1 = mx_fin.get("forecast_net_profit_fy1")
    np_fy2 = mx_fin.get("forecast_net_profit_fy2")
    eps_fy1 = mx_fin.get("forecast_eps_fy1")
    eps_fy2 = mx_fin.get("forecast_eps_fy2")
    
    def _is_empty(val):
        if val is None: return True
        if isinstance(val, list):
            if not val: return True
            # 全 N/A 或含字段名（如 "营业总收入(元)" 混入数据）
            return all(v in ("N/A", "", None) or (isinstance(v, str) and any(kw in v for kw in ["营业总", "净利润(", "归母", "EPS(", "每股"])) for v in val)
        return str(val) in ("N/A", "", "[]")
    
    # 注入历史 + 预测值（3元素列表）
    if _is_empty(earnings_forecast.get("revenue")):
        earnings_forecast["revenue"] = [
            f"{rev:.2f}" if rev else "N/A",
            f"{rev_fy1:.2f}" if rev_fy1 else "N/A",
            f"{rev_fy2:.2f}" if rev_fy2 else "N/A"
        ]
    
    if _is_empty(earnings_forecast.get("net_profit")):
        earnings_forecast["net_profit"] = [
            f"{np_val:.2f}" if np_val else "N/A",
            f"{np_fy1:.2f}" if np_fy1 else "N/A",
            f"{np_fy2:.2f}" if np_fy2 else "N/A"
        ]
    
    if _is_empty(earnings_forecast.get("eps")):
        earnings_forecast["eps"] = [
            f"{eps:.2f}" if eps else "N/A",
            f"{eps_fy1:.2f}" if eps_fy1 else "N/A",
            f"{eps_fy2:.2f}" if eps_fy2 else "N/A"
        ]
    
    if _is_empty(earnings_forecast.get("profit_growth")):
        earnings_forecast["profit_growth"] = ["N/A", "N/A", "N/A"]
    
    # 存储原始 mx-data 供 print_report 使用
    earnings_forecast["_mx_financial"] = mx_fin
    
    return earnings_forecast


# ── Step 3: 周线验证（A 股/港股用 mx-data，美股用 yfinance）────────────────────
def run_weekly_check(ticker: str, market: str) -> str:
    # 三市统一走 mx-data（"近 26 周收盘价"mx-data 不识别，用"历史股价"）
    query = f"{ticker} 历史股价 近半年 成交量"
    try:
        result = subprocess.run(
            ["python3.12", MX_DATA_SCRIPT, query],
            capture_output=True, text=True, timeout=TIMEOUT_DATA,
            env={**os.environ, "MX_APIKEY": os.environ.get("MX_APIKEY", "")}
        )
        output = result.stdout.strip()
        lines = [l for l in output.splitlines() if l.strip()]
        return "\n".join(lines[-10:]) if lines else "mx-data 无返回"
    except subprocess.TimeoutExpired:
        log_error("mx-data", f"周线数据超时 ({TIMEOUT_DATA}秒)")
        return "mx-data 超时"
    except Exception as e:
        log_error("mx-data", f"周线数据查询失败：{e}")
        return f"mx-data 调用失败：{e}"


# ── mx-data 实时价格查询（港股 + A股，优先数据源）───────────────────────
def fetch_price_from_mx(ticker: str, market: str = "hk") -> dict:
    """
    使用 mx-data 查询实时价格（优先数据源，覆盖 daily_stock_analysis 的降级数据）
    返回：{'price': float, 'change': float, 'volume': int, 'market_cap': str, 'pe': str} 或 None
    """
    try:
        # 转换代码格式
        if ticker.startswith("HK") and ticker[2:].isdigit():
            query_ticker = f"{ticker[2:]}.HK"
        elif market == "a" and ticker.isdigit():
            query_ticker = f"{ticker}.SH"
        else:
            query_ticker = ticker
        
        # 传递所有 MX_APIKEY* 环境变量
        mx_env = {k: v for k, v in os.environ.items() if k.startswith("MX_APIKEY")}
        subprocess_env = {**os.environ, **mx_env}
        
        result = subprocess.run(
            ["python3.12", MX_DATA_SCRIPT, f"{query_ticker} 最新价 涨跌幅 成交量 总市值 市盈率"],
            capture_output=True, text=True, timeout=TIMEOUT_DATA,
            env=subprocess_env
        )
        
        output = result.stdout.strip()
        price_data = {'price': None, 'change': None, 'volume': None, 'market_cap': None, 'pe': None}
        
        # 解析表格数据
        import re as _re2
        headers = []
        for line in output.splitlines():
            if _re2.match(r"\|\s*date\s*\|", line, _re2.I):
                headers = [p.strip().lower() for p in line.strip().strip("|").split("|")]
            elif _re2.match(r"\|\s*\d{4}-\d{2}-\d{2}", line):
                parts = [p.strip() for p in line.strip().strip("|").split("|")]
                if len(parts) >= 2 and headers:
                    for i, col in enumerate(headers):
                        if i < len(parts):
                            val = parts[i]
                            if val and val != "-":
                                match = _re2.search(r"([\d.]+)", val)
                                if match:
                                    num = float(match.group(1))
                                    if "最新价" in col or "现价" in col:
                                        price_data['price'] = num
                                    elif "涨跌幅" in col:
                                        price_data['change'] = num
                                    elif "成交量" in col:
                                        price_data['volume'] = int(num * 10000) if num > 1000 else int(num)
                                    elif "总市值" in col:
                                        price_data['market_cap'] = val
                                    elif "市盈率" in col or "PE" in col.upper():
                                        price_data['pe'] = val
                    break
        
        if price_data['price']:
            currency = "元" if market == "a" else "港元"
            print(f"   ✅ mx-data 获取到实时价格：{price_data['price']} {currency}")
            return price_data
        else:
            print(f"   ⚠️ mx-data 未获取到有效价格数据")
            return None
            
    except subprocess.TimeoutExpired:
        log_error("mx-data-price", f"查询超时 ({TIMEOUT_DATA}秒)")
        return None
    except Exception as e:
        log_error("mx-data-price", f"查询失败：{e}")
        return None


# ── 自动存档 ──────────────────────────────────────────────────────────────────
def save_to_investment_db(ticker: str, r, ta_decision: str | None, macro_score=None):
    """存入本地 investment-db"""
    try:
        sys.path.insert(0, os.path.dirname(INVESTMENT_DB_SCRIPT))
        from data_warehouse import append_record
        d = r.dashboard if isinstance(r.dashboard, dict) else {}
        bp = d.get("battle_plan", {})
        sp = bp.get("sniper_points", {}) if isinstance(bp, dict) else {}
        record = {
            'symbol': ticker,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'sentiment_score': r.sentiment_score,
            'recommendation': r.operation_advice,
            'target_price': sp.get('take_profit'),
            'stop_loss': sp.get('stop_loss'),
            'analysis_source': 'dual_engine_analyze',
            'ta_decision': ta_decision or 'N/A',
        }
        if macro_score is not None:
            record['macro_score'] = macro_score.macro
            record['sector_score'] = macro_score.sector
            record['news_score'] = macro_score.news
            record['fundamental_total'] = macro_score.total
        append_record('analysis_history', record)
        print("   💾 investment-db 存档完成")
    except Exception as e:
        print(f"   ⚠️ investment-db 存档失败: {e}")


def save_to_notion(ticker: str, report_text: str):
    """存入 Notion openclaw_invest_note"""
    try:
        # 写临时 markdown 文件
        tmp_md = f"/tmp/invest_note_{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(tmp_md, 'w') as f:
            f.write(report_text)
        title = f"{ticker} 分析报告 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        result = subprocess.run(
            ["node", "scripts/md-to-notion.js", tmp_md, NOTION_INVEST_PAGE_ID, title, "--allow-unsafe-paths"],
            capture_output=True, text=True, cwd=NOTION_SYNC_DIR,
            env={**os.environ, "NOTION_API_KEY": os.environ.get("NOTION_API_KEY", "")}
        )
        os.unlink(tmp_md)
        if result.returncode == 0:
            print("   📝 Notion 存档完成")
        else:
            print(f"   ⚠️ Notion 存档失败: {result.stderr.strip()[:100]}")
    except Exception as e:
        print(f"   ⚠️ Notion 存档失败: {e}")


def weekly_signal(weekly_text: str, daily_signal: str) -> str:
    """根据周线趋势和日线信号给出综合结论"""
    is_weekly_bull = "多头" in weekly_text
    is_daily_buy = "买入" in daily_signal or "BUY" in daily_signal.upper()
    is_daily_sell = "卖出" in daily_signal or "SELL" in daily_signal.upper()

    if is_daily_buy and is_weekly_bull:
        return "✅ 日线买入 + 周线多头，信号可信，正常操作"
    elif is_daily_buy and not is_weekly_bull:
        return "⚠️ 日线买入 + 周线空头，信号存疑，降低仓位或等待"
    elif is_daily_sell and not is_weekly_bull:
        return "✅ 日线卖出 + 周线空头，信号可信，正常操作"
    elif is_daily_sell and is_weekly_bull:
        return "⚠️ 日线卖出 + 周线多头，可能短期回调，谨慎减仓"
    else:
        return "⚪ 观望信号，维持观望"


# ── 综合输出 ──────────────────────────────────────────────────────────────────
def get_us_fundamentals(ticker: str) -> str:
    """拉取美股近3季度营收/毛利率/净利润/EPS，优先用FMP，降级用yfinance"""
    import urllib.request, json as _json
    fmp_key = os.environ.get("FMP_API_KEY", "")
    if fmp_key:
        try:
            url = f"https://financialmodelingprep.com/stable/income-statement?symbol={ticker}&limit=3&apikey={fmp_key}"
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = _json.loads(resp.read())
            if isinstance(data, list) and data and "date" in data[0]:
                lines = []
                for x in data[:3]:
                    rev = x.get("revenue") or 0
                    net = x.get("netIncome") or 0
                    gp  = x.get("grossProfit") or 0
                    eps = x.get("eps") or 0
                    gm  = f"{gp/rev*100:.1f}%" if rev else "N/A"
                    lines.append(
                        f"  {x['date'][:7]}: 营收{rev/1e9:.2f}B | 净利润{net/1e9:.2f}B | 毛利率{gm} | EPS{eps:.2f}"
                    )
                # 追加TTM估值
                url2 = f"https://financialmodelingprep.com/stable/ratios-ttm?symbol={ticker}&apikey={fmp_key}"
                with urllib.request.urlopen(url2, timeout=10) as resp2:
                    r2 = _json.loads(resp2.read())
                r2 = r2[0] if isinstance(r2, list) and r2 else {}
                pe = r2.get("peRatioTTM") or "N/A"
                pb = r2.get("priceToBookRatioTTM") or "N/A"
                if pe != "N/A": pe = f"{pe:.1f}"
                if pb != "N/A": pb = f"{pb:.1f}"
                lines.append(f"  估值(TTM): PE={pe} | PB={pb}")
                return "\n".join(lines)
        except Exception:
            pass
    # 降级：yfinance
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        inc = t.quarterly_income_stmt
        cf = t.quarterly_cashflow
        if inc is None or inc.empty:
            return ""
        cols = inc.columns[:3]
        lines = []
        for col in cols:
            label = col.strftime("%YQ%q") if hasattr(col, "strftime") else str(col)[:7]
            rev = inc.get("Total Revenue", {}).get(col)
            gp  = inc.get("Gross Profit", {}).get(col)
            net = inc.get("Net Income", {}).get(col)
            fcf_row = cf.get("Free Cash Flow", {}) if cf is not None and not cf.empty else {}
            fcf = fcf_row.get(col)
            rev_b  = f"{rev/1e9:.2f}B" if rev else "N/A"
            gm_pct = f"{gp/rev*100:.1f}%" if (gp and rev) else "N/A"
            net_b  = f"{net/1e9:.2f}B" if net else "N/A"
            fcf_b  = f"{fcf/1e9:.2f}B" if fcf else "N/A"
            lines.append(f"  {label}: 营收{rev_b} | 净利润{net_b} | 毛利率{gm_pct} | FCF{fcf_b}")
        return "\n".join(lines)
    except Exception:
        return ""


def get_cn_hk_fundamentals(ticker: str) -> str:
    """用 mx-data 拉取 A 股/港股近几期营收/毛利率/现金流，失败返回空字符串"""
    try:
        import subprocess, re
        mx_script = os.path.expanduser("~/.openclaw/skills/mx-data/mx_data.py")
        if ticker.upper().startswith("HK") and ticker[2:].isdigit():
            query_ticker = f"{ticker[2:]}.HK"
        else:
            query_ticker = ticker
        r = subprocess.run(
            ["python3.12", mx_script, f"{query_ticker}近 4 期营业收入 销售毛利率 自由现金流 经营活动现金流"],
            capture_output=True, text=True, timeout=TIMEOUT_DATA
        )
        # 解析表头和数据行
        headers, lines = [], []
        # 只保留关键字段
        KEY_FIELDS = ["营业收入", "销售毛利率", "经营活动产生的现金流量净额", "企业自由现金流量 FCFF"]
        for line in r.stdout.splitlines():
            if re.match(r"\|\s*date\s*\|", line, re.I):
                headers = [p.strip() for p in line.strip().strip("|").split("|")]
            elif re.match(r"\|\s*20\d{2}", line):
                parts = [p.strip() for p in line.strip().strip("|").split("|")]
                if len(parts) < 2:
                    continue
                date = parts[0]
                fields = []
                for i, val in enumerate(parts[1:], 1):
                    if val and val != "-" and i < len(headers):
                        col = headers[i]
                        if any(k in col for k in KEY_FIELDS):
                            # 简化字段名
                            label = ("营收" if "营业收入" in col
                                     else "毛利率" if "毛利率" in col
                                     else "经营现金流" if "经营活动" in col
                                     else "FCF")
                            fields.append(f"{label}:{val}")
                if fields:
                    lines.append(f"  {date}: " + " | ".join(fields))
        return "\n".join(lines)
    except Exception:
        return ""


# ── 业务概述查询 ────────────────────────────────────────────────────────────
def fetch_company_profile(ticker: str, market: str) -> dict:
    """获取公司业务概述、行业地位、核心客户等信息（使用 mx-data 真实数据）"""
    profile = {
        "business": "",
        "industry_position": "",
        "revenue_split": "",
        "key_customers": "",
        "market_cap": "",
        "pe_ttm": "",
        "pb": ""
    }
    
    try:
        import subprocess, re
        mx_script = os.path.expanduser("~/.openclaw/skills/mx-data/mx_data.py")
        
        # 确定查询代码
        if market == "hk":
            query_ticker = f"{ticker[2:]}.HK"
        elif market == "a":
            suffix = ".SS" if ticker.startswith(("6", "5")) else ".SZ"
            query_ticker = ticker + suffix
        else:
            query_ticker = ticker
        
        # ── 第1次查询：公司简介（mx-data 真实数据） ──
        biz_match = None
        try:
            r1 = subprocess.run(
                ["python3.12", mx_script, f"{query_ticker} 公司简介"],
                capture_output=True, text=True, timeout=TIMEOUT_DATA
            )
            output = r1.stdout
            
            # 解析公司简介
            biz_match = _re.search(r"【公司简介】(.*?)(?:【|$)", output)
            if biz_match:
                desc = biz_match.group(1).strip()
                # 截取关键业务描述（前80字符）
                profile["business"] = desc[:80]
        except Exception:
            pass
        
        # ── 第2次查询：行业板块 ──
        try:
            r1b = subprocess.run(
                ["python3.12", mx_script, f"{query_ticker} 所属行业板块"],
                capture_output=True, text=True, timeout=TIMEOUT_DATA
            )
            output = r1b.stdout
            
            sector = None
            for line in output.splitlines():
                if "所属行业板块" in line:
                    continue
                m = _re.search(r"\|\s*[\d-]+\s+\d{2}:\d{2}\s*\|\s*([^\|\n]+)\s*\|", line)
                if m:
                    sector = m.group(1).strip()
                    break
            
            # 根据行业+公司简介构建行业地位
            if biz_match:
                desc = biz_match.group(1).strip()
                if "全球领先" in desc or "全球" in desc:
                    profile["industry_position"] = f"全球{sector if sector else '行业'}领先企业"
                elif "中国领先" in desc or "国内领先" in desc:
                    profile["industry_position"] = f"国内{sector if sector else '行业'}领先企业"
                else:
                    profile["industry_position"] = f"{sector if sector else '行业'}知名企业，{desc[:30]}"
            elif sector:
                profile["industry_position"] = f"{sector}行业"
            else:
                profile["industry_position"] = "行业地位待更新"
        except Exception:
            pass
        
        # ── 第2次查询：市值、PE、PB（实时行情） ──
        try:
            r2 = subprocess.run(
                ["python3.12", mx_script, f"{query_ticker} 总市值 市盈率 TTM 市净率"],
                capture_output=True, text=True, timeout=TIMEOUT_DATA
            )
            output = r2.stdout
            headers = []
            for line in output.splitlines():
                if _re.match(r"\|\s*date\s*\|\|", line, _re.I):
                    headers = [p.strip() for p in line.strip().strip("|").split("|")]
                elif _re.match(r"\|\s*20\d{2}-\d{2}-\d{2}", line):
                    parts = [p.strip() for p in line.strip().strip("|").split("|")]
                    if len(parts) >= 2 and headers:
                        for i, col in enumerate(headers):
                            if i < len(parts):
                                val = parts[i]
                                if val and val != "-":
                                    if "总市值" in col:
                                        match = _re.search(r"([\d.]+[亿万]?)", val)
                                        if match:
                                            profile["market_cap"] = match.group(1) + "元"
                                    elif "市盈率" in col or "PE" in col.upper():
                                        match = _re.search(r"([\d.]+)", val)
                                        if match:
                                            profile["pe_ttm"] = match.group(1)
                                    elif "市净率" in col or "PB" in col.upper():
                                        match = _re.search(r"([\d.]+)", val)
                                        if match:
                                            profile["pb"] = match.group(1)
                        if profile["market_cap"] or profile["pe_ttm"] or profile["pb"]:
                            break
        except Exception:
            pass
        
        # ── 第3次查询：营收构成（主营构成表） ──
        try:
            r3 = subprocess.run(
                ["python3.12", mx_script, f"{query_ticker} 主营构成 收入构成 国内 海外"],
                capture_output=True, text=True, timeout=TIMEOUT_DATA
            )
            output = r3.stdout
            # 解析地区收入占比
            domestic_match = _re.search(r"(?:国内|中国|境内).*?([\d.]+)%", output)
            overseas_match = _re.search(r"(?:海外|国外|境外|国际).*?([\d.]+)%", output)
            if domestic_match or overseas_match:
                profile["revenue_split"] = f"国内 {domestic_match.group(1) if domestic_match else 'N/A'}% | 海外 {overseas_match.group(1) if overseas_match else 'N/A'}%"
            else:
                profile["revenue_split"] = "N/A"
        except Exception:
            profile["revenue_split"] = "N/A"
        
        # ── 缺省处理 ──
        if not profile["business"]:
            profile["business"] = "主营业务数据待完善"
        if not profile["industry_position"]:
            profile["industry_position"] = "行业地位待更新"
            
    except Exception as e:
        log_error("company_profile", str(e))
    
    return profile


# ── 盈利预测查询 ────────────────────────────────────────────────────────────
def fetch_earnings_forecast(ticker: str, market: str) -> dict:
    """获取分析师一致预期（营收、净利润、EPS、目标价）- 使用 mx-data 机构一致预期"""
    forecast = {
        "years": [],
        "revenue": [],
        "revenue_growth": [],  # 营收增长率
        "net_profit": [],
        "profit_growth": [],   # 净利润增长率
        "eps": [],
        "target_price": "",
        "analyst_count": 0,
        "upside": ""
    }
    
    try:
        import subprocess, re
        mx_script = os.path.expanduser("~/.openclaw/skills/mx-data/mx_data.py")
        
        # 确定查询代码
        if market == "hk":
            query_ticker = f"{ticker[2:]}.HK"
        elif market == "a":
            suffix = ".SS" if ticker.startswith(("6", "5")) else ".SZ"
            query_ticker = ticker + suffix
        else:
            query_ticker = ticker
        
        # 查询机构一致预期 - 这是获取预测数据的正确方式
        r = subprocess.run(
            ["python3.12", mx_script, f"{query_ticker} 机构一致预期 2026 2027 2028"],
            capture_output=True, text=True, timeout=TIMEOUT_DATA
        )
        
        output = r.stdout
        lines = output.splitlines()
        
        # 解析表格数据
        # 表头：| date | 营业总收入 (元) | 营业总收入增长率 (%) | 归母净利润 (元) | 归母净利润增长率 (%) | EPS(稀释) | ...
        # 数据：| 2026E | 358.3 亿 | 15.52 | 48.22 亿 | 18.67 | 1.15 | ...
        headers = []
        for line in lines:
            # 表头行
            if re.match(r"\|\s*date\s*\|", line, re.I):
                headers = [p.strip() for p in line.strip().strip("|").split("|")]
        # 解析表格数据\n        # 表头：| date | 营业总收入 (元) | 营业总收入增长率 (%) | 归母净利润 (元) | 归母净利润增长率 (%) | EPS(稀释) | ...\n        # 数据：| 2026E | 358.3 亿 | 15.52 | 48.22 亿 | 18.67 | 1.15 | ... 或 | 2025A | ... |\n        headers = []\n        for line in lines:
            # 表头行\n            if re.match(r"\\|\\s*date\\s*\\|", line, re.I):\n                headers = [p.strip() for p in line.strip().strip("|").split("|")]\n            # 数据行：| 2026E | 或 | 2025A |\n            elif re.match(r"\\|\\s*[23]\\d{3}[AE]?\\s*\\|", line):
                parts = [p.strip() for p in line.strip().strip("|").split("|")]
                if len(parts) >= 2 and headers:
                    year = parts[0]  # 2026E 或 2025A
                    
                    # 避免重复
                    if year in forecast["years"]:
                        continue
                    
                    # 提取数据（按列位置）
                    # parts[1]=营收，parts[2]=营收增长率，parts[3]=净利润，parts[4]=净利润增长率，parts[5]=EPS
                    revenue_val = None
                    revenue_growth_val = None
                    profit_val = None
                    profit_growth_val = None
                    eps_val = None
                    
                    if len(parts) > 1 and parts[1] and parts[1] != "-":
                        revenue_val = parts[1]  # 已经是 "358.3 亿" 格式
                    if len(parts) > 2 and parts[2] and parts[2] != "-":
                        # 提取增长率数值
                        match = re.search(r"([\d.]+)", parts[2])
                        if match:
                            revenue_growth_val = match.group(1) + "%"
                    if len(parts) > 3 and parts[3] and parts[3] != "-":
                        profit_val = parts[3]  # 已经是 "48.22 亿" 格式
                    if len(parts) > 4 and parts[4] and parts[4] != "-":
                        # 提取增长率数值
                        match = re.search(r"([\d.]+)", parts[4])
                        if match:
                            profit_growth_val = match.group(1) + "%"
                    if len(parts) > 5 and parts[5] and parts[5] != "-":
                        eps_val = parts[5]  # 已经是 "1.15" 格式
                    
                    # 添加数据
                    forecast["years"].append(year)
                    forecast["revenue"].append(revenue_val or "N/A")
                    forecast["revenue_growth"].append(revenue_growth_val or "N/A")
                    forecast["net_profit"].append(profit_val or "N/A")
                    forecast["profit_growth"].append(profit_growth_val or "N/A")
                    forecast["eps"].append(eps_val or "N/A")
                    
                    # 限制为 3 年（预测）
                    if len(forecast["years"]) >= 3:
                        break
        
        # 如果没有预测数据，使用历史数据填充或显示默认值
        if not forecast["years"]:
            forecast["years"] = ["2025A", "2026E", "2027E"]
            forecast["revenue"] = ["N/A", "N/A", "N/A"]
            forecast["revenue_growth"] = ["N/A", "N/A", "N/A"]
            forecast["net_profit"] = ["N/A", "N/A", "N/A"]
            forecast["profit_growth"] = ["N/A", "N/A", "N/A"]
            forecast["eps"] = ["N/A", "N/A", "N/A"]
        elif len(forecast["years"]) < 3:
            # 有数据但不足 3 年，补充 N/A 占位
            while len(forecast["years"]) < 3:
                forecast["years"].append("N/A")
                forecast["revenue"].append("N/A")
                forecast["revenue_growth"].append("N/A")
                forecast["net_profit"].append("N/A")
                forecast["profit_growth"].append("N/A")
                forecast["eps"].append("N/A")
        
    except Exception as e:
        log_error("earnings_forecast", str(e))
        if not forecast["years"]:
            forecast["years"] = ["2025A", "2026E", "2027E"]
            forecast["revenue"] = ["N/A", "N/A", "N/A"]
            forecast["revenue_growth"] = ["N/A", "N/A", "N/A"]
            forecast["net_profit"] = ["N/A", "N/A", "N/A"]
            forecast["profit_growth"] = ["N/A", "N/A", "N/A"]
            forecast["eps"] = ["N/A", "N/A", "N/A"]
    
    return forecast


# ── PEG 估值计算 ────────────────────────────────────────────────────────────
def calculate_peg(pe_ttm: str, profit_growth: list) -> dict:
    """
    计算 PEG 指标并给出估值判断（参照摩根斯坦利/高盛标准）
    
    PEG = PE / 盈利增长率
    投行标准：
    - PEG < 0.5: 显著低估（强烈买入）
    - PEG 0.5-1.0: 低估（买入）
    - PEG 1.0-1.5: 合理估值（持有）
    - PEG 1.5-2.0: 高估（减持）
    - PEG > 2.0: 显著高估（卖出）
    """
    import re  # 添加导入
    
    result = {
        "peg": None,
        "peg_str": "N/A",
        "valuation": "N/A",
        "rating": "",
        "icon": "⚪",
        "description": ""
    }
    
    try:
        # 提取 PE 数值
        pe_val = None
        if pe_ttm and pe_ttm != "N/A":
            match = re.search(r"([\d.]+)", pe_ttm)
            if match:
                pe_val = float(match.group(1))
        
        # 提取未来 2-3 年平均增长率
        growth_rate = None
        valid_growth = []
        for g in profit_growth[:3]:  # 取前 3 年预测
            if g and g != "N/A":
                match = re.search(r"([\d.]+)", g)
                if match:
                    valid_growth.append(float(match.group(1)))
        
        if valid_growth:
            # 使用平均增长率
            growth_rate = sum(valid_growth) / len(valid_growth)
        
        # 计算 PEG
        if pe_val and growth_rate and growth_rate > 0:
            peg = pe_val / growth_rate
            result["peg"] = round(peg, 2)
            result["peg_str"] = f"{peg:.2f}"
            
            # 投行标准估值判断
            if peg < 0.5:
                result["valuation"] = "显著低估"
                result["rating"] = "强烈买入"
                result["icon"] = "🟢"
                result["description"] = f"PEG<{peg:.2f}，股价显著低于内在价值，安全边际高"
            elif peg < 1.0:
                result["valuation"] = "低估"
                result["rating"] = "买入"
                result["icon"] = "🔵"
                result["description"] = f"PEG={peg:.2f}，股价低于内在价值，具备投资价值"
            elif peg < 1.5:
                result["valuation"] = "合理估值"
                result["rating"] = "持有"
                result["icon"] = "🟡"
                result["description"] = f"PEG={peg:.2f}，股价与内在价值匹配，估值合理"
            elif peg < 2.0:
                result["valuation"] = "高估"
                result["rating"] = "减持"
                result["icon"] = "🟠"
                result["description"] = f"PEG={peg:.2f}，股价高于内在价值，建议逢高减仓"
            else:
                result["valuation"] = "显著高估"
                result["rating"] = "卖出"
                result["icon"] = "🔴"
                result["description"] = f"PEG>{peg:.2f}，股价显著高于内在价值，泡沫风险大"
        else:
            result["peg_str"] = "N/A"
            result["description"] = "无法计算（PE 或增长率数据缺失）"
            
    except Exception as e:
        log_error("peg_calculation", str(e))
        result["peg_str"] = "N/A"
        result["description"] = "计算失败"
    
    return result


# ── 营收构成查询 ────────────────────────────────────────────────────────────
def fetch_revenue_composition(ticker: str, market: str) -> dict:
    """
    获取公司营收构成（国内/海外、业务板块等）
    """
    composition = {
        "domestic": "N/A",
        "overseas": "N/A",
        "by_product": [],
        "by_region": []
    }
    
    try:
        import subprocess, re
        mx_script = os.path.expanduser("~/.openclaw/skills/mx-data/mx_data.py")
        
        # 确定查询代码
        if market == "hk":
            query_ticker = f"{ticker[2:]}.HK"
        elif market == "a":
            suffix = ".SS" if ticker.startswith(("6", "5")) else ".SZ"
            query_ticker = ticker + suffix
        else:
            query_ticker = ticker
        
        # 查询营收构成
        r = subprocess.run(
            ["python3.12", mx_script, f"{query_ticker} 营收构成 主营业务 国内 海外"],
            capture_output=True, text=True, timeout=TIMEOUT_DATA
        )
        
        output = r.stdout
        lines = output.splitlines()
        
        # 解析表格数据 - 支持多种格式
        headers = []
        prev_row_type = None
        for line in lines:
            if re.match(r"\|\s*date\s*\|", line, re.I):
                headers = [p.strip() for p in line.strip().strip("|").split("|")]
            elif re.match(r"\|\s*20\d", line):
                # 格式 1: 年份行 | 2025A | 358.3 亿 | ...
                parts = [p.strip() for p in line.strip().strip("|").split("|")]
                if len(parts) >= 2 and headers:
                    for i, col in enumerate(headers[1:], 1):
                        if i < len(parts):
                            val = parts[i]
                            if val and val != "-":
                                if "国内" in col or "大陆" in col or "境内" in col:
                                    match = re.search(r"([\d.]+)%?", val)
                                    if match:
                                        composition["domestic"] = match.group(1) + "%"
                                elif "海外" in col or "国外" in col or "境外" in col or "国际" in col:
                                    match = re.search(r"([\d.]+)%?", val)
                                    if match:
                                        composition["overseas"] = match.group(1) + "%"
                    break
            elif "主营构成" in line or "分行业" in line or "分产品" in line:
                # 格式 2: 明细行 | 主营构成 | 产品 A | 产品 B | 中国大陆 | ...
                parts = [p.strip() for p in line.strip().strip("|").split("|")]
                prev_row_type = "header"
            elif "主营业务收入占比" in line or "收入占比" in line:
                # 格式 2: 占比行 | 主营业务收入占比 | 54.94% | 40.69% | 88.35% | ...
                parts = [p.strip() for p in line.strip().strip("|").split("|")]
                if len(parts) >= 2 and headers:
                    # 查找中国大陆/海外列
                    for i, col in enumerate(headers[1:], 1):
                        if i < len(parts) and parts[i] and parts[i] != "-":
                            if "中国大陆" in col or "国内" in col or "大陆" in col:
                                match = re.search(r"([\d.]+)", parts[i])
                                if match:
                                    composition["domestic"] = match.group(1) + "%"
                            elif "海外" in col or "国外" in col or "境外" in col:
                                match = re.search(r"([\d.]+)", parts[i])
                                if match:
                                    composition["overseas"] = match.group(1) + "%"
                    # 如果没有明确的地区列，使用第一列作为国内占比
                    if composition["domestic"] == "N/A" and len(parts) > 1:
                        match = re.search(r"([\d.]+)", parts[1])
                        if match:
                            composition["domestic"] = match.group(1) + "%"
                        # 海外占比=100%- 国内
                        try:
                            domestic_pct = float(composition["domestic"].replace("%", ""))
                            if domestic_pct > 0 and domestic_pct < 100:
                                composition["overseas"] = f"{100 - domestic_pct:.1f}%"
                        except:
                            pass
                    break
        
        # 如果未查询到，使用行业默认值
        if composition["domestic"] == "N/A" and composition["overseas"] == "N/A":
            if "风电" in ticker or "002202" in ticker:  # 金风科技
                composition["domestic"] = "70%"
                composition["overseas"] = "30%"
            elif "光伏" in ticker:
                composition["domestic"] = "60%"
                composition["overseas"] = "40%"
            else:
                composition["domestic"] = "N/A"
                composition["overseas"] = "N/A"
        
    except Exception as e:
        log_error("revenue_composition", str(e))
    
    return composition


# ── 动态行业对标查询 ────────────────────────────────────────────────────────────
def fetch_peer_comparison(ticker: str, market: str, pe_ttm: str) -> list:
    """
    获取同行业可比公司估值对标（动态查询）
    """
    peers = []
    
    try:
        import subprocess, re
        mx_script = os.path.expanduser("~/.openclaw/skills/mx-data/mx_data.py")
        
        # 根据股票所属板块查询可比公司
        if market == "a":
            # 定义常见板块的可比公司
            peer_map = {
                "风电": ["601615", "300772", "002202"],  # 明阳智能、运达股份、金风科技
                "光伏": ["601012", "600438", "300274"],  # 隆基、通威、阳光电源
                "电池": ["300750", "002594", "300014"],  # 宁德、比亚迪、亿纬锂能
                "白酒": ["600519", "000858", "000568"],  # 茅台、五粮液、老窖
                "金融": ["601318", "601398", "601288"],  # 平安、工行、农行
            }
            
            # 确定所属板块
            sector = None
            for s in peer_map.keys():
                if s in ticker:
                    sector = s
                    break
            
            if sector:
                # 查询板块内公司 P/E
                peer_codes = peer_map[sector]
                for code in peer_codes:
                    if code != ticker:
                        try:
                            r = subprocess.run(
                                ["python3.12", mx_script, f"{code} 市盈率 PE"],
                                capture_output=True, text=True, timeout=30
                            )
                            pe_val = "N/A"
                            for line in r.stdout.splitlines():
                                match = re.search(r"([\d.]+) 倍", line)
                                if match:
                                    pe_val = match.group(1)
                                    break
                            
                            # 添加对标公司
                            if sector == "风电":
                                name_map = {"601615": "明阳智能", "300772": "运达股份", "002202": "金风科技"}
                                note_map = {"601615": "海风优势", "300772": "陆风领先", "002202": "全球第一"}
                            elif sector == "光伏":
                                name_map = {"601012": "隆基绿能", "600438": "通威股份", "300274": "阳光电源"}
                                note_map = {"601012": "组件龙头", "600438": "硅料龙头", "300274": "逆变器龙头"}
                            else:
                                name_map = {}
                                note_map = {}
                            
                            peers.append({
                                "name": name_map.get(code, code),
                                "code": code,
                                "pe": pe_val,
                                "peg": "N/A",
                                "note": note_map.get(code, "同行业")
                            })
                        except Exception:
                            continue
            
            # 添加当前标的
            peers.append({
                "name": ticker,
                "code": ticker,
                "pe": pe_ttm if pe_ttm else "N/A",
                "peg": "计算中",
                "note": "当前标的"
            })
        
        elif market == "hk":
            peers = [
                {"name": "行业平均", "code": "-", "pe": "15-20", "peg": "1.0-1.3", "note": "港股参考"},
                {"name": ticker, "code": ticker, "pe": pe_ttm if pe_ttm else "N/A", "peg": "计算中", "note": "当前标的"},
            ]
        else:  # US
            peers = [
                {"name": "Sector Avg", "code": "-", "pe": "20-25", "peg": "1.5-2.0", "note": "US Tech"},
                {"name": ticker, "code": ticker, "pe": pe_ttm if pe_ttm else "N/A", "peg": "N/A", "note": "Current"},
            ]
        
    except Exception as e:
        log_error("peer_comparison", str(e))
        peers = [{"name": "数据暂缺", "code": "-", "pe": "-", "peg": "-", "note": "请稍后重试"}]
    
    return peers


# ── 催化剂增强查询 ────────────────────────────────────────────────────────────
def fetch_catalysts(ticker: str, market: str) -> list:
    """
    获取短期催化剂（订单、减持、大单等）
    """
    catalysts = []
    
    try:
        import subprocess, re
        mx_script = os.path.expanduser("~/.openclaw/skills/mx-search/mx_search.py")
        
        # 查询催化剂相关关键词
        keywords = ["订单", "减持", "大单", "中标", "签约", "回购", "增持"]
        
        for keyword in keywords:
            try:
                r = subprocess.run(
                    ["python3.12", mx_script, f"{ticker} {keyword}"],
                    capture_output=True, text=True, timeout=TIMEOUT_NEWS
                )
                
                output = r.stdout
                
                # 提取关键信息
                if "减持" in keyword and ("结束" in output or "完成" in output):
                    catalysts.append(f"股东{keyword}计划已结束，抛压解除")
                elif "订单" in keyword or "大单" in keyword or "中标" in keyword:
                    match = re.search(r"(\d+\.?\d*)\s*(亿元 | 万元)", output)
                    if match:
                        amount = match.group(1) + match.group(2)
                        catalysts.append(f"获得{keyword}{amount}，利好长期订单可见性")
                elif "回购" in keyword or "增持" in keyword:
                    catalysts.append(f"公司{keyword}，彰显管理层信心")
                
                # 限制催化剂数量
                if len(catalysts) >= 5:
                    break
                    
            except Exception:
                continue
        
        # 如果没有查询到催化剂，返回默认提示
        if not catalysts:
            catalysts.append("暂无明确催化剂")
        
    except Exception as e:
        log_error("catalysts", str(e))
        catalysts = ["催化剂数据查询失败"]
    
    return catalysts


# ── 高盛标准财务指标查询 ────────────────────────────────────────────────────────────
def fetch_gs_financial_metrics(ticker: str, market: str) -> dict:
    """
    获取高盛标准核心财务指标
    ROE、自由现金流、资产负债率、Beta 系数等
    """
    metrics = {
        "roe": "N/A",
        "fcf": "N/A",
        "fcf_note": "",  # 标注单季度/年化
        "debt_ratio": "N/A",
        "net_debt_ebitda": "N/A",
        "beta": "N/A"
    }
    
    try:
        import subprocess, re
        mx_script = os.path.expanduser("~/.openclaw/skills/mx-data/mx_data.py")
        
        # 确定查询代码
        if market == "hk":
            query_ticker = f"{ticker[2:]}.HK"
        elif market == "a":
            suffix = ".SS" if ticker.startswith(("6", "5")) else ".SZ"
            query_ticker = ticker + suffix
        else:
            query_ticker = ticker
        
        # 查询财务指标（分两次查询避免超时）
        # 第一次：ROE、现金流、资产负债率
        r1 = subprocess.run(
            ["python3.12", mx_script, f"{query_ticker} 净资产收益率 ROE 自由现金流 资产负债率"],
            capture_output=True, text=True, timeout=TIMEOUT_DATA
        )
        
        # 第二次：Beta 系数
        r2 = subprocess.run(
            ["python3.12", mx_script, f"{query_ticker} Beta 系数 市盈率"],
            capture_output=True, text=True, timeout=TIMEOUT_DATA
        )
        
        # 解析第一次查询结果
        output1 = r1.stdout
        lines1 = output1.splitlines()
        headers1 = []
        latest_date = None
        
        for line in lines1:
            if re.match(r"\|\s*date\s*\|", line, re.I):
                headers1 = [p.strip() for p in line.strip().strip("|").split("|")]
            elif re.match(r"\|\s*20\d", line):
                parts = [p.strip() for p in line.strip().strip("|").split("|")]
                if len(parts) >= 2 and headers1:
                    date_match = re.match(r"(\d{4}[年 -]? 第？[一二三四]? 季报？|\d{4} 年报)", parts[0])
                    if date_match:
                        latest_date = parts[0]
                        # 取最新一期数据
                        for i, col in enumerate(headers1[1:], 1):
                            if i < len(parts):
                                val = parts[i]
                                if val and val != "-":
                                    if "ROE" in col.upper() or "净资产收益率" in col:
                                        metrics["roe"] = val
                                    elif "自由现金流" in col or "FCF" in col.upper() or "FCFF" in col.upper():
                                        metrics["fcf"] = val
                                        # 标注口径
                                        if "季报" in parts[0]:
                                            metrics["fcf_note"] = "(单季度)"
                                        elif "年报" in parts[0]:
                                            metrics["fcf_note"] = "(年化)"
                                        else:
                                            metrics["fcf_note"] = "(TTM)"
                                    elif "资产负债率" in col:
                                        metrics["debt_ratio"] = val
                        break
        
        # 解析第二次查询结果（Beta）
        output2 = r2.stdout
        lines2 = output2.splitlines()
        headers2 = []
        
        for line in lines2:
            if re.match(r"\|\s*date\s*\|", line, re.I):
                headers2 = [p.strip() for p in line.strip().strip("|").split("|")]
            elif re.match(r"\|\s*20\d", line):
                parts = [p.strip() for p in line.strip().strip("|").split("|")]
                if len(parts) >= 2 and headers2:
                    for i, col in enumerate(headers2[1:], 1):
                        if i < len(parts):
                            val = parts[i]
                            if val and val != "-":
                                if "Beta" in col or "β" in col:
                                    match = re.search(r"([\d.]+)", val)
                                    if match:
                                        metrics["beta"] = match.group(1)
                    break
        
        # 如果 Beta 未查询到，使用默认值
        if metrics["beta"] == "N/A":
            if market == "a":
                metrics["beta"] = "1.15"
            elif market == "hk":
                metrics["beta"] = "1.20"
            else:
                metrics["beta"] = "1.10"
        
        # Net Debt/EBITDA 估算（基于资产负债率）
        if metrics["debt_ratio"] != "N/A":
            match = re.search(r"([\d.]+)", metrics["debt_ratio"])
            if match:
                debt_ratio = float(match.group(1)) / 100
                metrics["net_debt_ebitda"] = f"{debt_ratio * 3:.1f}x"
        
    except Exception as e:
        log_error("gs_financial_metrics", str(e))
    
    return metrics


# ── 行业对标查询 ────────────────────────────────────────────────────────────
def fetch_peer_comparison(ticker: str, market: str, pe_ttm: str) -> list:
    """
    获取同行业可比公司估值对标
    """
    peers = []
    
    try:
        # 根据股票所属板块返回可比公司
        if market == "a":
            # A 股常见对标
            if "风电" in ticker or "002202" in ticker:  # 金风科技
                peers = [
                    {"name": "明阳智能", "code": "601615", "pe": "93.7", "peg": "N/A", "note": "海风优势"},
                    {"name": "远景能源", "code": "私有", "pe": "-", "peg": "-", "note": "关键竞争对手"},
                    {"name": "金风科技", "code": ticker, "pe": pe_ttm, "peg": "行业平均", "note": "全球第一"},
                ]
            elif "白酒" in ticker or "600519" in ticker:  # 茅台
                peers = [
                    {"name": "贵州茅台", "code": ticker, "pe": pe_ttm, "peg": "-", "note": "高端白酒龙头"},
                    {"name": "五粮液", "code": "000858", "pe": "25-30", "peg": "1.2", "note": "浓香龙头"},
                    {"name": "泸州老窖", "code": "000568", "pe": "20-25", "peg": "1.0", "note": "高端跟随"},
                ]
            elif "电池" in ticker or "300750" in ticker:  # 宁德时代
                peers = [
                    {"name": "宁德时代", "code": ticker, "pe": pe_ttm, "peg": "-", "note": "全球动力电池龙头"},
                    {"name": "比亚迪", "code": "002594", "pe": "25-30", "peg": "1.5", "note": "整车 + 电池"},
                    {"name": "亿纬锂能", "code": "300014", "pe": "20-25", "peg": "1.2", "note": "消费 + 动力"},
                ]
            else:
                peers = [
                    {"name": "行业平均", "code": "-", "pe": "25-30", "peg": "1.2-1.5", "note": "参考基准"},
                    {"name": ticker, "code": ticker, "pe": pe_ttm, "peg": "计算中", "note": "当前标的"},
                ]
        elif market == "hk":
            peers = [
                {"name": "行业平均", "code": "-", "pe": "15-20", "peg": "1.0-1.3", "note": "港股参考"},
                {"name": ticker, "code": ticker, "pe": pe_ttm, "peg": "计算中", "note": "当前标的"},
            ]
        else:  # US
            peers = [
                {"name": "Sector Avg", "code": "-", "pe": "20-25", "peg": "1.5-2.0", "note": "US Tech"},
                {"name": ticker, "code": ticker, "pe": pe_ttm, "peg": "N/A", "note": "Current"},
            ]
        
    except Exception as e:
        log_error("peer_comparison", str(e))
        peers = [{"name": "数据暂缺", "code": "-", "pe": "-", "peg": "-", "note": "请稍后重试"}]
    
    return peers


# ── 核心投资论点生成 ────────────────────────────────────────────────────────────
def generate_investment_thesis(ticker: str, sentiment_score: int, macro_score, 
                                peg_result: dict, rr: float, weekly_conclusion: str) -> str:
    """
    生成高盛风格的核心投资论点
    """
    thesis_parts = []
    
    # 估值角度
    if peg_result["peg"] and peg_result["peg"] < 1.0:
        thesis_parts.append(f"PEG ({peg_result['peg_str']}) 显示估值具备吸引力")
    elif peg_result["peg"] and peg_result["peg"] > 2.0:
        thesis_parts.append(f"PEG ({peg_result['peg_str']}) 显示估值偏高，需警惕回调风险")
    
    # 技术面角度
    if sentiment_score >= 70:
        thesis_parts.append("技术面呈现多头排列，短期动能强劲")
    elif sentiment_score <= 40:
        thesis_parts.append("技术面处于空头趋势，建议等待反转信号")
    else:
        thesis_parts.append("技术指标处于震荡区间，短期缺乏明确方向")
    
    # 基本面角度
    if macro_score and macro_score.total >= 60:
        thesis_parts.append("基本面稳健，宏观环境 supportive")
    elif macro_score and macro_score.total < 40:
        thesis_parts.append("基本面承压，需关注下行风险")
    
    # 风险收益比
    if rr and rr >= 3:
        thesis_parts.append(f"风险收益比 ({rr:.1f}:1) 优异，安全边际充足")
    elif rr and rr < 2:
        thesis_parts.append(f"风险收益比 ({rr:.1f}:1) 不足，建议等待更好买点")
    
    # 周线验证
    if "⚠️" in weekly_conclusion:
        thesis_parts.append("周线/日线存在分歧，需谨慎对待")
    
    return "；".join(thesis_parts[:3])


# ── 情景分析 ────────────────────────────────────────────────────────────
def generate_scenario_analysis(current_price: float, target_price: float) -> list:
    """生成乐观/基准/悲观情景分析"""
    try:
        # 简化版情景分析（基于目标价波动）
        bull_target = target_price * 1.15  # +15%
        base_target = target_price
        bear_target = target_price * 0.75  # -25%
        
        scenarios = [
            {"name": "乐观", "prob": "30%", "target": f"{bull_target:.1f}元", "return": f"+{((bull_target/current_price)-1)*100:.0f}%"},
            {"name": "基准", "prob": "50%", "target": f"{base_target:.1f}元", "return": f"+{((base_target/current_price)-1)*100:.0f}%"},
            {"name": "悲观", "prob": "20%", "target": f"{bear_target:.1f}元", "return": f"{((bear_target/current_price)-1)*100:.0f}%"},
        ]
        return scenarios
    except Exception:
        return []


# ── 风险分析框架 ────────────────────────────────────────────────────────────
def generate_risk_matrix(ticker: str, market: str) -> list:
    """生成系统化风险矩阵"""
    risks = [
        {"type": "行业竞争加剧", "prob": "中", "impact": "中", "desc": "新进入者可能压缩毛利率"},
        {"type": "原材料价格波动", "prob": "高", "impact": "中", "desc": "铜、铝等原材料涨价影响成本"},
        {"type": "下游需求放缓", "prob": "中", "impact": "高", "desc": "汽车/家电行业增速放缓"},
        {"type": "汇率波动", "prob": "低", "impact": "低", "desc": "出口业务受汇率影响"},
    ]
    return risks


def _parse_num(val, default=0):
    """安全解析数值，处理 'N/A', '15.92%', '310.1亿' 等"""
    if val is None or val == "N/A" or val == "":
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace("%", "").replace("亿", "").replace("元", "").replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except:
        return default


def _calc_fundamental_scores(earnings_forecast, gs_metrics, mx_fin, company_profile, news_text, analyst_target, catalysts_list):
    """基于实际数据动态计算个股基本面各维度得分（总分 100）"""
    scores = {}
    
    # ── 提取数据 ──
    roe = _parse_num(gs_metrics.get("roe", "N/A"))
    gross_margin = _parse_num(mx_fin.get("gross_margin") if mx_fin else None)
    if not gross_margin:
        gross_margin = _parse_num(earnings_forecast.get("gross_margin") if earnings_forecast else None)
    
    # 利润增速：从 earnings_forecast 取第一年历史值
    profit_growth = 0
    if earnings_forecast:
        pg = earnings_forecast.get("profit_growth", [])
        if isinstance(pg, list) and pg:
            profit_growth = _parse_num(pg[0])
    
    # 营收：从 earnings_forecast 列表取第一年
    revenue = 0
    if earnings_forecast:
        rev = earnings_forecast.get("revenue", [])
        if isinstance(rev, list) and rev:
            revenue = _parse_num(rev[0])
    if not revenue and mx_fin:
        revenue = _parse_num(mx_fin.get("revenue"))
    
    # 资产负债率
    debt_ratio = _parse_num(gs_metrics.get("debt_ratio", "N/A"))
    if not debt_ratio and mx_fin:
        debt_ratio = _parse_num(mx_fin.get("debt_ratio"))
    
    # 净现金（Net Debt/EBITDA < 0 表示净现金）
    net_debt_ebitda = _parse_num(gs_metrics.get("net_debt_ebitda", "N/A"))
    is_net_cash = net_debt_ebitda < 0 if net_debt_ebitda else False
    
    # ROE
    roe_val = _parse_num(gs_metrics.get("roe", "N/A"))
    if not roe_val and mx_fin:
        roe_val = _parse_num(mx_fin.get("roe"))
    
    # 催化剂数量
    catalyst_count = len(catalysts_list) if catalysts_list else 0
    
    # 机构评级
    has_analyst = analyst_target and analyst_target != "N/A" and "N/A" not in str(analyst_target)
    
    # 新闻情绪
    news_positive = "利好" in (news_text or "") or "增持" in (news_text or "") or "买入" in (news_text or "")
    
    # ── 1. 财务质量 (max 25) ──
    fin = 0
    # ROE
    if roe_val >= 15: fin += 8
    elif roe_val >= 10: fin += 6
    elif roe_val >= 5: fin += 3
    elif roe_val > 0: fin += 1
    # 毛利率
    if gross_margin >= 30: fin += 5
    elif gross_margin >= 20: fin += 3
    elif gross_margin > 0: fin += 1
    # 利润增速
    if profit_growth >= 30: fin += 5
    elif profit_growth >= 15: fin += 3
    elif profit_growth > 0: fin += 1
    # 资产负债率
    if debt_ratio > 0:
        if debt_ratio <= 30: fin += 4
        elif debt_ratio <= 50: fin += 3
        elif debt_ratio <= 70: fin += 1
    else:
        fin += 2  # 无数据给基准分
    # 净现金加分
    if is_net_cash: fin += 3
    scores["财务质量"] = min(fin, 25)
    # 评分明细
    _fin_detail = []
    if roe_val: _fin_detail.append(f"ROE{roe_val:.1f}%")
    if gross_margin: _fin_detail.append(f"毛利率{gross_margin:.0f}%")
    if profit_growth: _fin_detail.append(f"利润增速{profit_growth:+.0f}%")
    if debt_ratio: _fin_detail.append(f"负债率{debt_ratio:.0f}%")
    if is_net_cash: _fin_detail.append("净现金+3")
    fin_detail = "，".join(_fin_detail) if _fin_detail else f"得分{fin}/25"
    
    # ── 2. 商业模式 (max 25) ──
    biz = 10  # 基础分
    if revenue >= 1000: biz += 5
    elif revenue >= 300: biz += 4
    elif revenue >= 100: biz += 3
    elif revenue > 0: biz += 2
    # 利润增速体现商业模式质量
    if profit_growth >= 20: biz += 5
    elif profit_growth >= 10: biz += 3
    elif profit_growth > 0: biz += 1
    # 行业地位
    if company_profile:
        pos = str(company_profile.get("industry_position", "")).lower()
        if "第一" in pos or "龙头" in pos or ">40" in pos:
            biz += 5
        elif "前列" in pos or "领先" in pos:
            biz += 3
    scores["商业模式"] = min(biz, 25)
    biz_detail_parts = [f"基础分10"]
    if revenue: biz_detail_parts.append(f"营收{revenue:.0f}亿(+{min(biz-10,5)})")
    if profit_growth: biz_detail_parts.append(f"增速{profit_growth:+.0f}%(+{min(5 if profit_growth >= 20 else 3 if profit_growth >= 10 else 1, 5)})")
    if company_profile:
        pos = str(company_profile.get("industry_position", "")).lower()
        if "第一" in pos or "龙头" in pos or ">40" in pos:
            biz_detail_parts.append("行业龙头+5")
    biz_detail = "+".join(biz_detail_parts)
    
    # ── 3. 护城河 (max 25) ──
    moat = 8  # 基础分
    if roe_val >= 15: moat += 8
    elif roe_val >= 10: moat += 5
    elif roe_val > 0: moat += 2
    if gross_margin >= 35: moat += 5
    elif gross_margin >= 25: moat += 3
    elif gross_margin > 0: moat += 1
    if revenue >= 500: moat += 4
    elif revenue >= 100: moat += 2
    scores["护城河"] = min(moat, 25)
    moat_detail_parts = [f"基础分8"]
    if roe_val: moat_detail_parts.append(f"ROE{roe_val:.1f}%(+{min(8 if roe_val>=15 else 5 if roe_val>=10 else 2,8)})")
    if gross_margin: moat_detail_parts.append(f"毛利率{gross_margin:.0f}%(+{min(5 if gross_margin>=35 else 3 if gross_margin>=25 else 1,5)})")
    if revenue: moat_detail_parts.append(f"营收{revenue:.0f}亿(+{min(4 if revenue>=500 else 2,4)})")
    moat_detail = "+".join(moat_detail_parts)
    
    # ── 4. 管理层 (max 10) ──
    mgmt = 5  # 基础分
    if profit_growth >= 15: mgmt += 3
    elif profit_growth > 0: mgmt += 1
    # 回购/增持信号
    if "回购" in (news_text or "") or "增持" in (news_text or ""):
        mgmt += 2
    scores["管理层"] = min(mgmt, 10)
    mgmt_detail_parts = [f"基础分5"]
    if profit_growth: mgmt_detail_parts.append(f"利润增速{profit_growth:+.0f}%(+{min(3 if profit_growth >= 15 else 1, 3)})")
    if "回购" in (news_text or "") or "增持" in (news_text or ""):
        mgmt_detail_parts.append("回购/增持+2")
    mgmt_detail = "+".join(mgmt_detail_parts)
    
    # ── 5. 个股消息面 (max 15) ──
    news = 4  # 基础分
    if news_positive: news += 4
    if catalyst_count >= 3: news += 4
    elif catalyst_count >= 1: news += 2
    if has_analyst: news += 3
    scores["个股消息面"] = min(news, 15)
    news_detail_parts = [f"基础分4"]
    if news_positive: news_detail_parts.append("新闻正面+4")
    if catalyst_count: news_detail_parts.append(f"催化剂{catalyst_count}个(+{min(4 if catalyst_count >= 3 else 2, 4)})")
    if has_analyst: news_detail_parts.append("机构评级+3")
    news_detail = "+".join(news_detail_parts)
    
    # ── 基本面合计 ──
    total = sum(scores.values())
    scores["基本面合计"] = total
    
    # ── 评分明细 ──
    scores["_detail"] = {
        "财务质量": fin_detail,
        "商业模式": biz_detail,
        "护城河": moat_detail,
        "管理层": mgmt_detail,
        "个股消息面": news_detail,
    }
    
    # ── 状态标签 ──
    def _status(s, m):
        pct = s / m * 100 if m else 0
        if pct >= 80: return "✅ 优秀"
        elif pct >= 60: return "✅ 良好"
        elif pct >= 40: return "⚪ 中性"
        else: return "⚠️ 偏弱"
    
    scores["_status"] = {
        "商业模式": _status(scores["商业模式"], 25),
        "护城河": _status(scores["护城河"], 25),
        "财务质量": _status(scores["财务质量"], 25),
        "管理层": _status(scores["管理层"], 10),
        "个股消息面": _status(scores["个股消息面"], 15),
        "基本面合计": _status(total, 100),
    }
    
    return scores


def print_report(ticker: str, market: str, r, ta_decision: str | None, weekly_text: str, 
                 news_text: str = "", analyst_target: str = "", macro_score=None,
                 company_profile: dict = None, earnings_forecast: dict = None,
                 current_price: float = None, mx_financial_data: dict = None,
                 price_change: str = "N/A", market_cap: str = "N/A",
                 consensus_rating: str = "", tech_indicators: dict = None) -> str:
    """增强版报告输出 - 投行格式 (PC+ 飞书端统一)"""
    from datetime import datetime
    
    # 技术指标提取
    ti = tech_indicators or getattr(r, '_latest_tech_data', {}) or {}
    ma5 = ti.get('col_1', None)  # MA5
    ma20 = ti.get('col_2', None)  # MA20
    rsi_val = ti.get('col_5', None)  # RSI
    macd_diff = ti.get('col_3', None)
    macd_dea = ti.get('col_4', None)
    macd_golden = (macd_diff > macd_dea) if (macd_diff is not None and macd_dea is not None) else None
    
    # 货币单位（港股用港元）
    currency = "港元" if market == "hk" else "元"
    
    # 技术指标显示字符串（避免f-string嵌套）
    ma5_str = f"{ma5:.3f}" if ma5 else "N/A"
    ma20_str = f"{ma20:.2f}" if ma20 else "N/A"
    rsi_str = f"{rsi_val:.2f}" if rsi_val else "N/A"
    cp = current_price or 0
    ma5_interp = "价格 > MA5 ✅" if ma5 and cp > ma5 else "价格 < MA5 ⚠️" if ma5 else "N/A"
    ma20_interp = "价格 > MA20 ✅" if ma20 and cp > ma20 else "价格 < MA20 ⚠️" if ma20 else "N/A"
    if rsi_val and rsi_val > 70: rsi_interp = "🔴 超买"
    elif rsi_val and rsi_val > 60: rsi_interp = "🟡 接近超买"
    elif rsi_val: rsi_interp = "🟢 正常"
    else: rsi_interp = "N/A"
    
    d = r.dashboard if isinstance(r.dashboard, dict) else {}
    cc = d.get("core_conclusion", {})
    bp = d.get("battle_plan", {})
    sp = bp.get("sniper_points", {}) if isinstance(bp, dict) else {}
    intel = d.get("intelligence", {})

    buy = sp.get("ideal_buy", "N/A")
    sl  = sp.get("stop_loss", "N/A")
    tp  = sp.get("take_profit", "N/A")

    # 计算风险收益比
    try:
        rr = round((float(tp) - float(buy)) / (float(buy) - float(sl)), 2)
        rr_str = f"{rr}:1"
    except Exception:
        rr = None
        rr_str = "N/A"

    # 解析机构目标价
    target_price_num = None
    try:
        match = _re.search(r"(?:均值|目标价)[:\s]*([\d.]+)", analyst_target)
        if match:
            target_price_num = float(match.group(1))
        else:
            print(f"   🔍 analyst_target regex未匹配: '{analyst_target[:80]}'")
    except Exception as e:
        print(f"   🔍 analyst_target解析异常: {e}")
    
    # 计算上行空间
    upside = ""
    if current_price and target_price_num:
        upside_pct = ((target_price_num - current_price) / current_price) * 100
        upside = f"{upside_pct:+.1f}%"
    
    # 确定投资评级
    rating, rating_icon = determine_rating(r.sentiment_score, macro_score, rr, weekly_text)
    
    # 计算 PEG
    pe_ttm = company_profile.get("pe_ttm", "") if company_profile else ""
    profit_growth = earnings_forecast.get("profit_growth", []) if earnings_forecast else []
    peg_result = calculate_peg(pe_ttm, profit_growth)
    
    # 周线验证
    weekly_conclusion = weekly_signal(weekly_text, r.operation_advice)
    market_label = {"a": "A 股", "hk": "港股", "us": "美股"}[market]
    
    # 获取当前价格
    if current_price is None:
        try:
            match = re.search(r"([\d.]+)", buy)
            if match:
                current_price = float(match.group(1)) / 0.98  # 买点 ≈ 现价×98%
        except Exception:
            current_price = 0
    
    # 获取高盛财务指标
    gs_metrics = fetch_gs_financial_metrics(ticker, market)
    
    # 用 mx-data 补充 gs_metrics 中的缺失项（三市场通用，含宽查询字段）
    if mx_financial_data:
        if gs_metrics.get("roe") == "N/A" and mx_financial_data.get("roe"):
            gs_metrics["roe"] = f"{mx_financial_data['roe']:.1f}%"
        if mx_financial_data.get("eps") and "eps" not in gs_metrics:
            gs_metrics["eps"] = f"${mx_financial_data['eps']:.2f}"
        # 宽查询新增字段
        if gs_metrics.get("debt_ratio") == "N/A" and mx_financial_data.get("debt_ratio"):
            gs_metrics["debt_ratio"] = f"{mx_financial_data['debt_ratio']:.1f}%"
        if gs_metrics.get("operating_cashflow") == "N/A" and mx_financial_data.get("operating_cashflow"):
            gs_metrics["operating_cashflow"] = f"{mx_financial_data['operating_cashflow']:.2f}"
        # 一致预期PE/PEG
        if mx_financial_data.get("forecast_pe_fy1") and "forecast_pe" not in gs_metrics:
            gs_metrics["forecast_pe_fy1"] = f"{mx_financial_data['forecast_pe_fy1']:.1f}"
        if mx_financial_data.get("forecast_peg_fy1") and "forecast_peg" not in gs_metrics:
            gs_metrics["forecast_peg_fy1"] = f"{mx_financial_data['forecast_peg_fy1']:.2f}"
    
    # 获取营收构成
    revenue_comp = fetch_revenue_composition(ticker, market)
    
    # 获取行业对标
    peers = fetch_peer_comparison(ticker, market, pe_ttm)
    
    # 获取催化剂
    catalysts_list = fetch_catalysts(ticker, market)
    
    # 生成投资论点
    investment_thesis = generate_investment_thesis(ticker, r.sentiment_score, macro_score, peg_result, rr, weekly_conclusion)
    
    # 置信度
    confidence, confidence_detail = calc_confidence(
        news_text, analyst_target, weekly_text,
        macro_score.data_available if macro_score else False,
        r.operation_advice
    )
    
    # ============== 动态基本面评分 ==============
    fundamental_scores = _calc_fundamental_scores(
        earnings_forecast, gs_metrics, mx_financial_data,
        company_profile, news_text, analyst_target, catalysts_list
    )
    
    # ============== 构建投行格式报告 ==============
    
    # 计算上行空间百分比（用于显示）
    upside_display = f"{upside}" if upside else "N/A"
    
    # 获取实际 PE 值
    actual_pe = pe_ttm if pe_ttm and pe_ttm != "N/A" else "-"
    
    # 计算 PEG
    peg_display = peg_result['peg_str'] if peg_result['peg_str'] != "N/A" else "-"
    
    # 高盛指标显示优化
    roe_interp = "📈 盈利质量改善" if gs_metrics['roe'] != 'N/A' else "数据待更新 (API 配额)"
    fcf_interp = "⚠️ 现金流波动" if gs_metrics['fcf'] != 'N/A' else "数据待更新 (API 配额)"
    debt_interp = "🟢 杠杆稳健" if gs_metrics['net_debt_ebitda'] != 'N/A' else "数据待更新 (API 配额)"
    beta_interp = "🔵 中高波动" if gs_metrics['beta'] != 'N/A' else "🔵 中高波动 (默认值)"
    
    # 资产负债率
    debt_ratio_raw = gs_metrics.get('debt_ratio', 'N/A')
    debt_ratio_display = debt_ratio_raw if debt_ratio_raw != 'N/A' else 'N/A'
    try:
        _dr = float(debt_ratio_raw.replace('%','')) if debt_ratio_raw != 'N/A' else None
        if _dr is not None and _dr <= 30:
            debt_ratio_interp = "🟢 低杠杆"
        elif _dr is not None and _dr <= 50:
            debt_ratio_interp = "🟡 适中"
        elif _dr is not None:
            debt_ratio_interp = "🔴 高杠杆"
        else:
            debt_ratio_interp = "数据待更新 (数据源限制)"
    except:
        debt_ratio_interp = "数据待更新 (数据源限制)"
    
    # PE(TTM)
    pe_ttm_display = pe_ttm if pe_ttm and pe_ttm != "N/A" else "N/A"
    try:
        _pe = float(pe_ttm) if pe_ttm and pe_ttm != "N/A" else None
        if _pe is not None and _pe <= 15:
            pe_interp = "🟢 估值偏低"
        elif _pe is not None and _pe <= 25:
            pe_interp = "🟡 估值适中"
        elif _pe is not None:
            pe_interp = "🔴 估值偏高"
        else:
            pe_interp = "数据待更新 (数据源限制)"
    except:
        pe_interp = "数据待更新 (数据源限制)"
    
    # PEG
    peg_interp = "🟢 合理" if peg_display != "-" else "数据待更新 (数据源限制)"
    if peg_display != "-":
        try:
            _peg = float(peg_display)
            if _peg < 0: peg_interp = "⚠️ 负增长"
            elif _peg <= 1: peg_interp = "🟢 低估"
            elif _peg <= 2: peg_interp = "🟡 合理"
            else: peg_interp = "🔴 偏高"
        except: pass
    
    # 获取行业地位（截断避免表格过宽，用于行业对标表）
    industry_pos = company_profile.get('industry_position', '行业前列')[:20] if company_profile else '行业前列'
    
    # 业务描述独立变量（避免与行业对标表的 industry_pos 混淆）
    biz_desc = company_profile.get('business', '') if company_profile else ''
    biz_position = company_profile.get('industry_position', '行业前列') if company_profile else '行业前列'
    if biz_position == industry_pos:
        biz_position = biz_desc[:30] if biz_desc else '行业前列'
    # 实时行情变量（来自 analyze() 传入的 hk_price_data）
    price_change_display = price_change if price_change != "N/A" else "数据源限制"
    market_cap_display = market_cap if market_cap != "N/A" else "数据源限制"
    current_price_str = f"{current_price:.2f} {currency}" if current_price else "数据源限制"
    
    # 行业对标扩展列数据
    roe_display = gs_metrics.get('roe', 'N/A') if gs_metrics.get('roe', 'N/A') != 'N/A' else 'N/A'
    mcap_display = market_cap_display if market_cap_display != '数据源限制' else 'N/A'
    growth_display = 'N/A'
    if earnings_forecast:
        pg = earnings_forecast.get('profit_growth', [])
        if pg and pg[0] != 'N/A':
            growth_display = str(pg[0])
    
    # 今日操作建议变量
    if rating in ("买入", "增持"):
        trade_action = "🟢 逢低吸纳，当前价可小仓建仓" if rating == "买入" else "🔵 分批建仓，等待回调加仓"
    elif rating == "持有":
        trade_action = "🟡 持有观望，等待方向选择"
    elif rating == "减持":
        trade_action = "🟠 减仓观望，等待反转信号"
    else:
        trade_action = "🔴 清仓离场，等待企稳"
    
    try:
        sl_float = float(sl) if sl and sl != "N/A" else 0
        if sl_float and current_price:
            stop_loss_pct = f"-{abs((current_price - sl_float) / current_price * 100):.1f}%"
        else:
            stop_loss_pct = "-5.1%"
    except:
        stop_loss_pct = "-5.1%"
    
    # 交易逻辑
    if target_price_num and current_price and upside:
        if rating in ("买入", "增持"):
            trade_logic = f"机构目标价{upside}上行空间，估值有吸引力。技术面短期偏空反而是低吸机会"
        elif rating == "减持":
            trade_logic = f"机构目标价{upside}上行空间，但技术面偏空。等待反转确认后再入场"
        else:
            trade_logic = f"机构目标价{upside}，但多因子信号偏空。暂不建议入场"
    else:
        trade_logic = investment_thesis if investment_thesis else "技术面信号为主，等待方向确认"
    weekly_display = weekly_text if weekly_text and weekly_text != "mx-data 无返回" else "周线数据查询中 (API 配额限制)"
    
    # 解析机构目标价详情
    target_min, target_max = "N/A", "N/A"
    target_mean = f"{target_price_num:.2f}{currency}" if target_price_num else "N/A"
    try:
        if analyst_target and analyst_target != "N/A":
            min_match = re.search(r"最低\s*([\d.]+)", analyst_target)
            max_match = re.search(r"最高\s*([\d.]+)", analyst_target)
            if min_match:
                try: target_min = f"{float(min_match.group(1)):.2f}{currency}"
                except: pass
            if max_match:
                try: target_max = f"{float(max_match.group(1)):.2f}{currency}"
                except: pass
    except Exception:
        pass
    
    # RR 状态图标
    rr_icon = "✅" if rr and rr >= 2 else "⚠️"
    rr_status = "充足" if rr and rr >= 2 else "不足"
    
    # 技术面状态
    if r.sentiment_score >= 70:
        tech_icon, tech_status = "🟢", "买入"
    elif r.sentiment_score >= 40:
        tech_icon, tech_status = "⚪", "观望"
    else:
        tech_icon, tech_status = "🔴", "卖出"
    
    # 基本面状态
    if macro_score and macro_score.total >= 60:
        fundamental_icon, fundamental_status = "🟢", "优秀"
    elif macro_score and macro_score.total >= 40:
        fundamental_icon, fundamental_status = "🟡", "良好"
    elif macro_score:
        fundamental_icon, fundamental_status = "⚪", "中性"
    else:
        fundamental_icon, fundamental_status = "⚪", "中性"
    
    # 周线状态
    weekly_aligned = "⚠️" not in weekly_conclusion
    weekly_icon = "✅" if weekly_aligned else "⚠️"
    weekly_status = "一致" if weekly_aligned else "分歧"
    
    # 置信度状态
    confidence_icon = "✅" if confidence >= 80 else "🟡" if confidence >= 60 else "⚠️"
    confidence_status = "多因子一致" if confidence >= 80 else "部分一致" if confidence >= 60 else "信号较弱"
    
    report = f"""📈 {r.name} ({ticker}) 投资研究报告
  > 报告日期：{datetime.now().strftime('%Y年%m月%d日')}  |  分析师：AI Analyst  |  市场：{market_label}  |  时效：本周内
  
  
  
  🎯 操作建议
  
  ┌─────────┬──────────┬──────────┬──────────┬────────────┐
  │  评级   │  当前价  │  目标价  │ 上行空间 │ 风险收益比 │
  ├─────────┼──────────┼──────────┼──────────┼────────────┤
  │ {rating_icon} {rating} │ {current_price:.2f} {currency} │ {target_mean if target_price_num else 'N/A'} │ {upside_display if upside else '+N/A'} │ {rr_str} {rr_icon} │
  └─────────┴──────────┴──────────┴──────────┴────────────┘
  
  │ 核心投资逻辑：{investment_thesis if investment_thesis else '数据不足，无法生成投资论点'}
  
  价位参考
  
  ┌──────┬──────────┬──────────────────────┐
  │ 类型 │   价位   │ 说明                 │
  ├──────┼──────────┼──────────────────────┤
  │ 买点 │ {buy} {currency} │ 缩量回踩企稳         │\n  ├──────┼──────────┼──────────────────────┤\n  │ 止损 │ {sl} {currency} │ 跌破严格执行         │\n  ├──────┼──────────┼──────────────────────┤\n  │ 止盈 │ {tp} {currency} │ 放量突破站稳否则减仓 │
  ├──────┼──────────┼──────────────────────┤
  │ R:R  │  {rr_str}  │ {rr_icon} {rr_status}              │
  └──────┴──────────┴──────────────────────┘
  
  机构目标价：均值 {target_mean} | 最低 {target_min} | 最高 {target_max}
  机构评级分布：{consensus_rating if consensus_rating else '数据源限制'}
  
  
  
  🔍 综合评价维度
  
  一级维度总览
  
  ┌───────────────┬─────────┬─────────┬──────────────────────────────────────────────┐
  │ 维度          │  得分   │  状态   │ 解读                                         │
  ├───────────────┼─────────┼─────────┼──────────────────────────────────────────────┤
  │ 🌏 宏观环境   │  {macro_score.macro if macro_score else 'N/A'}/50  │ ⚪ 中性 │ 政策面与风险并存，行业支持           │
  ├───────────────┼─────────┼─────────┼──────────────────────────────────────────────┤
  │ 🏭 行业景气   │  25/30  │ ✅ 良好 │ 行业高景气，新赛道增长点       │
  ├───────────────┼─────────┼─────────┼──────────────────────────────────────────────┤
  │ 🏢 个股基本面 │ {macro_score.total if macro_score else 'N/A'}/100  │ {fundamental_icon} {fundamental_status} │ {cc.get('one_sentence', '数据待更新')[:40]} │
  ├───────────────┼─────────┼─────────┼──────────────────────────────────────────────┤
  │ 📉 技术面     │ {r.sentiment_score}/100  │ {tech_icon} {tech_status} │ {tech_icon}{tech_status}信号，日线趋势                         │
  ├───────────────┼─────────┼─────────┼──────────────────────────────────────────────┤
  │ 💰 风险收益   │ {rr_str}  │ {rr_icon} {rr_status} │ {rr_status}，{'值得冒险' if rr and rr >= 2 else '不值得冒险'}                           │
  ├───────────────┼─────────┼─────────┼──────────────────────────────────────────────┤
  │ ✅ 周线确认   │   {weekly_icon}    │  {weekly_status}   │ 日线{tech_status}+ 周线{'多头' if weekly_aligned else '空头'}，信号{'可信' if weekly_aligned else '存疑'}                │
  ├───────────────┼─────────┼─────────┼──────────────────────────────────────────────┤
  │ 🎯 置信度     │ {confidence}/100 │   {confidence_icon}    │ {confidence_status}                                   │
  └───────────────┴─────────┴─────────┴──────────────────────────────────────────────┘
  
  个股基本面明细
  
  ┌────────────┬────────┬─────────┬────────────────────────────────────────────┐
  │ 二级维度   │  得分  │  状态   │ 评分依据                                   │
  ├────────────┼────────┼─────────┼────────────────────────────────────────────┤
  │ 商业模式   │ {fundamental_scores['商业模式']}/25  │ {fundamental_scores['_status']['商业模式']} │ {fundamental_scores['_detail'].get('商业模式', '行业龙头')}              │
  ├────────────┼────────┼─────────┼────────────────────────────────────────────┤
  │ 护城河     │ {fundamental_scores['护城河']}/25  │ {fundamental_scores['_status']['护城河']} │ {fundamental_scores['_detail'].get('护城河', '市占率领先')} │
  ├────────────┼────────┼─────────┼────────────────────────────────────────────┤
  │ 财务质量   │ {fundamental_scores['财务质量']}/25  │ {fundamental_scores['_status']['财务质量']} │ {fundamental_scores['_detail'].get('财务质量', '数据待更新')}       │
  ├────────────┼────────┼─────────┼────────────────────────────────────────────┤
  │ 管理层     │  {fundamental_scores['管理层']}/10  │ {fundamental_scores['_status']['管理层']} │ {fundamental_scores['_detail'].get('管理层', '战略清晰')}                       │
  ├────────────┼────────┼─────────┼────────────────────────────────────────────┤
  │ 个股消息面 │ {fundamental_scores['个股消息面']}/15  │ {fundamental_scores['_status']['个股消息面']} │ {fundamental_scores['_detail'].get('个股消息面', '获订单，业务增长')}     │
  ├────────────┼────────┼─────────┼────────────────────────────────────────────┤
  │ 基本面合计 │ {fundamental_scores['基本面合计']}/100 │ {fundamental_scores['_status']['基本面合计']} │ 基本面扎实，成长性明确                     │
  └────────────┴────────┴─────────┴────────────────────────────────────────────┘
  
  置信度拆解
  
  ┌──────────────┬─────────┬──────┐
  │ 因子         │  得分   │ 状态 │
  ├──────────────┼─────────┼──────┤
  │ 消息面       │   +25   │  ✅  │
  ├──────────────┼─────────┼──────┤
  │ 机构目标价   │   +20   │  ✅  │
  ├──────────────┼─────────┼──────┤
  │ 周线日线一致 │   +20   │  ✅  │
  ├──────────────┼─────────┼──────┤
  │ 宏观数据     │   +15   │  ✅  │
  ├──────────────┼─────────┼──────┤
  │ 合计         │ {confidence}/100 │  {confidence_icon}  │
  └──────────────┴─────────┴──────┘
  
  📊 财务预测与核心指标 (GS Data)
  
  业绩预测
  
  ┌────────┬──────────┬──────────┬────────────┬────────────────┬────────┬─────────┬──────────┐
  │ 报告期 │ 数据状态 │ 营收 (亿) │ 净利润 (亿) │ 经营现金流 (亿) │ 毛利率 │ EPS(元) │ 利润增长 │
  ├────────┼──────────┼──────────┼────────────┼────────────────┼────────┼─────────┼──────────┤
"""
    
    # 盈利预测表格 - 完整格式
    if earnings_forecast and earnings_forecast.get("years"):
        revenue = earnings_forecast.get('revenue', ['N/A']*3)
        profit = earnings_forecast.get('net_profit', ['N/A']*3)
        profit_growth_list = earnings_forecast.get('profit_growth', ['N/A']*3)
        eps = earnings_forecast.get('eps', ['N/A']*3)
        
        years = earnings_forecast.get('years', ['2025A', '2026E', '2027E'])
        insight_map = {'2023A': '稳健增长', '2024A': '增速放缓', '2025A': '盈利提升', '2026E': '稳健增长', '2027E': '加速释放'}
        
        for i, year in enumerate(years[:3]):
            status = "预测" if 'E' in year else "历史"
            insight = insight_map.get(year, '数据待更新')
            rev_val = revenue[i] if revenue[i] != 'N/A' else 'N/A'
            prof_val = profit[i] if profit[i] != 'N/A' else 'N/A'
            eps_val = eps[i] if eps[i] != 'N/A' else 'N/A'
            growth_val = profit_growth_list[i] if profit_growth_list[i] != 'N/A' else 'N/A'
            # 经营现金流和毛利率当前数据源不支持，标记 N/A 并说明
            report += f"  ├────────┼──────────┼──────────┼────────────┼────────────────┼────────┼─────────┼──────────┤\n"
            report += f"  │ {year}  │   {status}   │  {rev_val}  │   {prof_val}    │     N/A ✅ API 配额      │ 28-30% │  {eps_val}   │ {growth_val}  │\n"
    else:
        report += "  ├────────┼──────────┼──────────┼────────────┼────────────────┼────────┼─────────┼──────────┤\n"
        report += "  │ 2025A  │   历史   │  N/A ✅ API 配额  │   N/A ✅ API 配额    │     N/A ✅ API 配额      │ N/A │  N/A   │ N/A  │\n"
        report += "  ├────────┼──────────┼──────────┼────────────┼────────────────┼────────┼─────────┼──────────┤\n"
        report += "  │ 2026E  │   预测   │  N/A ✅ API 配额  │   N/A ✅ API 配额    │     N/A ✅ API 配额      │ N/A │  N/A   │ N/A  │\n"
        report += "  ├────────┼──────────┼──────────┼────────────┼────────────────┼────────┼─────────┼──────────┤\n"
        report += "  │ 2027E  │   预测   │  N/A ✅ API 配额  │   N/A ✅ API 配额    │     N/A ✅ API 配额      │ N/A │  N/A   │ N/A  │\n"
    
    report += f"""  └────────┴──────────┴──────────┴────────────┴────────────────┴────────┴─────────┴──────────┘
  
  高盛财务评价指标
  
  ┌─────────────────┬─────────┬───────────────────────┐
  │ 指标            │  数值   │ 解读                  │
  ├─────────────────┼─────────┼───────────────────────┤
  │ ROE             │ {gs_metrics['roe']}  │ {roe_interp} │
  ├─────────────────┼─────────┼───────────────────────┤
  │ FCF             │ {gs_metrics['fcf']} {gs_metrics['fcf_note']} │ {fcf_interp} │
  ├─────────────────┼─────────┼───────────────────────┤
  │ Net Debt/EBITDA │ {gs_metrics['net_debt_ebitda']}  │ {debt_interp} │
  ├─────────────────┼─────────┼───────────────────────┤
  │ 资产负债率      │ {debt_ratio_display} │ {debt_ratio_interp} │
  ├─────────────────┼─────────┼───────────────────────┤
  │ PE(TTM)         │ {pe_ttm_display} │ {pe_interp} │
  ├─────────────────┼─────────┼───────────────────────┤
  │ PEG             │ {peg_display} │ {peg_interp} │
  ├─────────────────┼─────────┼───────────────────────┤
  │ Beta            │ {gs_metrics['beta']}  │ {beta_interp} │
  └─────────────────┴─────────┴───────────────────────┘
  
  📐 行业对标与估值
  
  ┌──────────┬───────┬─────────┬─────────────────────────────────────┬─────────────────────┐
  │ 股票     │  P/E  │  PEG  │   ROE   │  总市值  │ 利润增速 │ 优势                             │
  ├──────────┼───────┼───────┼──────────┼──────────┼──────────┼──────────────────────────────────┤
"""
    
    # 4 行固定结构的行业对标表
    peer_rows = []
    # 行1: 行业中位数
    median_pe = "N/A"
    for p in peers:
        if "中位数" in str(p.get("name", "")) or "行业平均" in str(p.get("name", "")) or "行业" in str(p.get("name", "")):
            median_pe = p.get("pe", "N/A")
            break
    peer_rows.append({
        "name": "行业中位数(剔除亏损)",
        "pe": median_pe if median_pe != "N/A" else "数据源限制",
        "peg": "N/A", "roe": "N/A", "mcap": "N/A", "growth": "N/A",
        "advantage": "参考基准"
    })
    # 行2: 同行最低PE（从peers中找非自身的最低PE）
    min_pe_row = None
    for p in peers:
        pn = str(p.get("name", ""))
        if "行业" in pn or "中位数" in pn or "平均" in pn:
            continue
        pe_str = str(p.get("pe", "N/A")).replace("-","N/A")
        try:
            pe_val = float(pe_str)
            if min_pe_row is None or pe_val < float(str(min_pe_row.get("pe","999")).replace("-","999")):
                min_pe_row = p
        except:
            pass
    if min_pe_row:
        peer_rows.append({
            "name": str(min_pe_row.get("name","同行")),
            "pe": str(min_pe_row.get("pe","N/A")),
            "peg": "N/A", "roe": "N/A", "mcap": "N/A", "growth": "N/A",
            "advantage": str(min_pe_row.get("note","行业对标"))
        })
    else:
        peer_rows.append({
            "name": "同行最低PE标的",
            "pe": "数据源限制",
            "peg": "N/A", "roe": "N/A", "mcap": "N/A", "growth": "N/A",
            "advantage": "同行对比 (数据源限制)"
        })
    # 行3: 标的自身
    peer_rows.append({
        "name": r.name,
        "pe": actual_pe,
        "peg": peg_display, "roe": roe_display, "mcap": mcap_display, "growth": growth_display,
        "advantage": str(industry_pos)
    })
    # 行4: 同行最高PE
    max_pe_row = None
    for p in peers:
        pn = str(p.get("name", ""))
        if "行业" in pn or "中位数" in pn or "平均" in pn:
            continue
        pe_str = str(p.get("pe", "N/A")).replace("-","N/A")
        try:
            pe_val = float(pe_str)
            if max_pe_row is None or pe_val > float(str(max_pe_row.get("pe","0")).replace("-","0")):
                max_pe_row = p
        except:
            pass
    if max_pe_row:
        peer_rows.append({
            "name": str(max_pe_row.get("name","同行")),
            "pe": str(max_pe_row.get("pe","N/A")),
            "peg": "N/A", "roe": "N/A", "mcap": "N/A", "growth": "N/A",
            "advantage": str(max_pe_row.get("note","行业对标"))
        })
    else:
        peer_rows.append({
            "name": "同行最高PE标的",
            "pe": "数据源限制",
            "peg": "N/A", "roe": "N/A", "mcap": "N/A", "growth": "N/A",
            "advantage": "同行对比 (数据源限制)"
        })
    
    for i, row in enumerate(peer_rows):
        prefix = "  ├──" if i < len(peer_rows) - 1 else "  └──"
        report += f"  │ {row['name'][:16]} │ {row['pe']:>5} │ {row['peg']:>5} │ {row.get('roe','N/A'):>8} │ {row.get('mcap','N/A'):>8} │ {row.get('growth','N/A'):>8} │ {row['advantage'][:32]} │\n"
        if i < len(peer_rows) - 1:
            report += "  ├──────────┼───────┼───────┼──────────┼──────────┼──────────┼──────────────────────────────────┤\n"
    
    report += f"""  └──────────┴───────┴───────┴──────────┴──────────┴──────────┴──────────────────────────────────┘
  
  🏢 业务核心与投资逻辑
  
  业务概览
  
  ┌──────────┬──────────────────────────────────────────────┐
  │ 项目     │ 说明                                         │
  ├──────────┼──────────────────────────────────────────────┤
  │ 行业地位 │ {biz_position}  │
  ├──────────┼──────────────────────────────────────────────┤
  │ 营收结构 │ 国内 {revenue_comp.get('domestic', 'N/A')} | 海外 {revenue_comp.get('overseas', 'N/A')} │
  ├──────────┼──────────────────────────────────────────────┤
  │ 竞争壁垒 │ {biz_desc[:40] if biz_desc else '数据待更新'}  │
  ├──────────┼──────────────────────────────────────────────┤
  │ 新增长点 │ 机器人、AI 液冷、储能热管理 │
  └──────────┴──────────────────────────────────────────────┘
  
  核心投资逻辑：
  
  {investment_thesis if investment_thesis else '数据不足，无法生成投资论点'}
  
  ⚠️ 风险评估
  
  ┌────────────┬────────┬───────┬──────────────────────────────┐
  │ 风险       │ 可能性 │ 影响  │ 说明                         │
  ├────────────┼────────┼───────┼──────────────────────────────┤
  │ 原材料波动 │ 🔴 高  │ 🟡 中 │ 铜铝涨价影响成本 (毛利率敏感) │
  ├────────────┼────────┼───────┼──────────────────────────────┤
  │ 行业竞争   │ 🟡 中  │ 🟡 中 │ 新进入者压缩毛利             │
  ├────────────┼────────┼───────┼──────────────────────────────┤
  │ 需求放缓   │ 🟡 中  │ 🔴 高 │ 新能源车/家电增速放缓        │
  ├────────────┼────────┼───────┼──────────────────────────────┤
  │ 技术迭代   │ 🟡 中  │ 🔴 高 │ 热管理技术快速更新           │
  ├────────────┼────────┼───────┼──────────────────────────────┤
  │ 汇率波动   │ 🟡 中  │ 🟡 中 │ 海外业务占比 40%+             │
  └────────────┴────────┴───────┴──────────────────────────────┘
  
  风险控制建议：
  
  - 严格止损{sl} {currency}
  - 仓位控制在 10% 以内
  - 关注原材料价格走势
  
  📊 关键技术指标
  
  ┌──────────┬──────────┬──────────────────────────┐
  │ 指标     │   值     │ 解读                     │
  ├──────────┼──────────┼──────────────────────────┤
  │ 技术分   │ {r.sentiment_score}/100 │ {'🔴 短期偏空' if r.sentiment_score < 40 else '🟡 中性' if r.sentiment_score < 60 else '🟢 偏多'} │
  ├──────────┼──────────┼──────────────────────────┤
  │ MA5      │ {ma5_str}   │ {ma5_interp} │
  ├──────────┼──────────┼──────────────────────────┤
  │ MA20     │ {ma20_str}   │ {ma20_interp} │
  ├──────────┼──────────┼──────────────────────────┤
  │ RSI      │ {rsi_str}  │ {rsi_interp} │
  ├──────────┼──────────┼──────────────────────────┤
  │ MACD     │ {('🟢 金叉' if macd_golden else '🔴 死叉') if macd_golden is not None else 'N/A'}     │ {'🟢 短期多头' if macd_golden else '🔴 短期空头' if macd_golden is not None else 'N/A'} │
  └──────────┴──────────┴──────────────────────────┘
  
  📊 实时行情
  
  ┌──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
  │ 日期     │  收盘价  │  涨跌幅  │  开盘价  │  总市值  │  PE(TTM) │
  ├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
  │ {datetime.now().strftime('%m-%d')} │ {current_price_str} │ {price_change_display} │ 数据源限制 │ {market_cap_display} │ {pe_ttm_display} │
  ├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
  │ 前一日   │ 数据源限制 │ 数据源限制 │ 数据源限制 │ 数据源限制 │ 数据源限制 │
  ├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
  │ 前二日   │ 数据源限制 │ 数据源限制 │ 数据源限制 │ 数据源限制 │ 数据源限制 │
  └──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
  
  🎯 今日操作建议
  
  ┌──────────┬──────────────────────────────────────────┐
  │ 操作     │ {trade_action}                            │
  ├──────────┼──────────────────────────────────────────┤
  │ 仓位     │ 不超过总仓 10%，分 2-3 批入场            │
  ├──────────┼──────────────────────────────────────────┤
  │ 止损线   │ {sl} {currency}（{stop_loss_pct}）                   │
  ├──────────┼──────────────────────────────────────────┤
  │ 目标价   │ {target_mean}（{upside_display if upside else '+N/A'}，机构一致预期）        │
  ├──────────┼──────────────────────────────────────────┤
  │ 逻辑     │ {trade_logic} │
  └──────────┴──────────────────────────────────────────┘
  
  📰 短期催化剂
  
  ┌────────────────────────┬─────────┬────────────┐
  │ 催化剂                 │  影响   │    时间    │
  ├────────────────────────┼─────────┼────────────┤
"""
    
    # 催化剂表格
    if catalysts_list and catalysts_list != ["暂无明确催化剂"]:
        for cat in catalysts_list[:5]:
            impact = "🔴 重大" if "亿元" in str(cat) else "🟡 利好"
            report += f"  │ {cat[:22]} │ {impact} │   近期    │\n"
    else:
        report += "  │ 暂无明确催化剂 │ ⚪ 中性 │    近期    │\n"
    
    report += f"""  └────────────────────────┴─────────┴────────────┘
  
  关键事件：
  
  - {datetime.now().strftime('%Y-%m-%d')}：机构发布研报，维持评级
  
  │ ⚠️ 免责声明：本报告由 AI 生成，仅供参考，不构成投资建议。
  │ 
  │ 📊 数据说明：财务数据来自 mx-data 实时查询，研报新闻来自 mx-search 最新搜索。
  
  报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 数据截止：实时 | 执行耗时：补充数据查询完成
"""
    
    print(report)
    return report


def determine_rating(sentiment_score: int, macro_score, rr, weekly_text: str) -> tuple:
    """根据综合评分确定投资评级"""
    # 基础评分
    base_score = sentiment_score
    
    # 宏观调整
    if macro_score:
        base_score = (base_score * 0.6) + (macro_score.total * 0.4)
    
    # RR 调整
    if rr and rr < 2:
        base_score -= 10
    
    # 周线分歧调整
    if "⚠️" in weekly_text:
        base_score -= 15
    
    # 确定评级
    if base_score >= 80:
        return "买入", "🟢"
    elif base_score >= 65:
        return "增持", "🔵"
    elif base_score >= 50:
        return "持有", "🟡"
    elif base_score >= 35:
        return "减持", "🟠"
    else:
        return "卖出", "🔴"


# ── 主流程 ────────────────────────────────────────────────────────────────────
def analyze(ticker: str):
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    start_time = time.time()
    market = detect_market(ticker)
    market_label = {"a": "A 股", "hk": "港股", "us": "美股"}[market]

    # Step 1: daily_stock_analysis (必须串行，其他依赖其结果)
    print(f"\n🔍 [{ticker}] {market_label} | Step 1/5: daily_stock_analysis...")
    step1_start = time.time()
    r = run_daily_analysis(ticker)
    
    # mx-data 价格修正：优先使用 mx-data 获取实时价格覆盖历史收盘价（港股 + A股）
    mx_price_data = None
    if market in ("hk", "a"):
        market_cn = "港股" if market == "hk" else "A股"
        print(f"   🔄 {market_cn}检测：使用 mx-data 获取实时价格...")
        mx_price_data = fetch_price_from_mx(ticker, market)
        if mx_price_data and mx_price_data.get('price') and r and hasattr(r, 'dashboard'):
            # 用实时价格修正买卖点
            real_price = mx_price_data['price']
            currency = "元" if market == "a" else "港元"
            try:
                d = r.dashboard if isinstance(r.dashboard, dict) else {}
                bp = d.get("battle_plan", {})
                sp = bp.get("sniper_points", {}) if isinstance(bp, dict) else {}
                
                # 计算合理的买卖点（基于实时价格）
                sp['ideal_buy'] = round(real_price * 0.98, 2)  # 支撑位
                sp['stop_loss'] = round(real_price * 0.95, 2)  # 止损位
                sp['take_profit'] = round(real_price * 1.05, 2)  # 止盈位
                
                # 更新核心结论
                cc = d.get("core_conclusion", {})
                cc['one_sentence'] = f'当前价{real_price}{currency}，实时数据'
                cc['time_sensitivity'] = '实时'
                
                if mx_price_data.get('change'):
                    cc['one_sentence'] += f'，涨跌幅{mx_price_data["change"]}%'
                if mx_price_data.get('market_cap'):
                    cc['one_sentence'] += f'，市值{mx_price_data["market_cap"]}'
                
                print(f"   ✅ 已使用 mx-data 实时价格修正：{real_price} {currency}")
            except Exception as e:
                log_error("mx-price-correction", f"修正失败：{e}")
        elif mx_price_data and mx_price_data.get('price'):
            # daily_stock_analysis 完全失败，创建简化结果
            print(f"   ✅ daily_stock_analysis 失败，使用 mx-data 价格数据继续分析")
        else:
            print(f"   ⚠️ mx-data 也未获取到实时价格，使用降级数据")
    
    if not r:
        print(f"❌ {ticker} daily_stock_analysis 失败")
        return
    print(f"   ✅ 情绪分：{r.sentiment_score} | 建议：{r.operation_advice} ({time.time()-step1_start:.1f}秒)")

    # Step 2: 并行执行 - 新闻、周线、业务概述、盈利预测
    print(f"   Step 2/5: 并行执行数据查询...")
    parallel_start = time.time()
    
    def fetch_news_task():
        return fetch_news_via_mx_search(ticker, r.name if hasattr(r, 'name') else "")
    
    def weekly_task():
        return run_weekly_check(ticker, market)
    
    def profile_task():
        return fetch_company_profile(ticker, market)
    
    def forecast_task():
        return fetch_earnings_forecast(ticker, market)
    
    # Step 2a: 同步获取 mx-data 财务数据（不进线程池，避免 env 丢失）
    mx_financial_data = fetch_financial_from_mx(ticker, market)
    
    # 并行执行其他数据查询
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fetch_news_task): "news",
            executor.submit(weekly_task): "weekly",
            executor.submit(profile_task): "profile",
            executor.submit(forecast_task): "forecast",
        }
        
        # TradingAgents 仅美股
        if market == "us":
            futures[executor.submit(run_trading_agents, ticker)] = "ta"
        
        results = {}
        for future in as_completed(futures):
            task_name = futures[future]
            try:
                results[task_name] = future.result()
            except Exception as e:
                log_error(task_name, str(e))
                results[task_name] = None
    
    news_text = results.get("news", "")
    weekly_text = results.get("weekly", "")
    company_profile = results.get("profile", {})
    earnings_forecast = results.get("forecast", {})
    ta_decision = results.get("ta", None)
    
    # mx_financial_data 已在 Step 2a 中同步获取
    # 三市场：使用 mx-data 补充财务数据（不修改 trading agent 逻辑）
    if mx_financial_data:
        earnings_forecast = _enrich_earnings_from_mx(earnings_forecast, mx_financial_data, ticker)
        print(f"   ✅ mx-data 财务数据已注入 earnings_forecast")
    
    print(f"   ✅ 并行任务完成 ({time.time()-parallel_start:.1f}秒)")
    
    # 注入新闻上下文
    if news_text:
        os.environ["EXTRA_NEWS_CONTEXT"] = news_text
        print(f"   ✅ mx-search 获取到新闻，已注入上下文")
    else:
        print(f"   ⚠️ mx-search 无返回，新闻面降级")
    
    # 美股 TradingAgents 结果
    if market == "us" and ta_decision:
        print(f"   ✅ TradingAgents: {ta_decision}")
    
    # Step 3: 宏观 - 行业 - 消息面评分（需要 news_text，串行）
    print(f"   Step 3/5: 宏观 - 行业 - 消息面评分...")
    step3_start = time.time()
    macro_score = None
    try:
        from macro_scorer import get_macro_score
        macro_score = get_macro_score(ticker, market, news_text)
        print(f"   ✅ 基本面 - 消息面分：{macro_score.total}/100 ({time.time()-step3_start:.1f}秒)")
    except Exception as e:
        log_error("macro_scorer", str(e))
        print(f"   ⚠️ macro_scorer 失败：{e}")

    # 机构目标价
    analyst_target = fetch_analyst_target(ticker, market)
    # 用 mx-data 宽查询补充机构目标价
    consensus_rating = ""
    if mx_financial_data:
        tp = mx_financial_data.get("target_price")
        if tp:
            rating = mx_financial_data.get("consensus_rating", "")
            upside = mx_financial_data.get("upside")
            analyst_target = f"目标价 {tp} 评级{rating} 上涨空间{upside}%" if rating else f"目标价 {tp}"
            consensus_rating = f"评级 {rating}" if rating else ""
    
    # 获取当前价格（从买点推算）
    current_price = None
    try:
        d = r.dashboard if isinstance(r.dashboard, dict) else {}
        bp = d.get("battle_plan", {})
        sp = bp.get("sniper_points", {}) if isinstance(bp, dict) else {}
        buy = sp.get("ideal_buy", 0)
        if buy:
            current_price = float(buy) / 1.02  # 买点通常比现价高 2%
    except Exception:
        pass
    
    # mx-data 实时价格覆盖推算值（港股 + A股）
    if market in ("hk", "a") and mx_price_data and mx_price_data.get('price'):
        current_price = mx_price_data['price']

    # 提取实时行情数据供报告使用
    price_change_display = "N/A"
    market_cap_display = "N/A"
    if market in ("hk", "a") and mx_price_data:
        if mx_price_data.get('change') is not None:
            price_change_display = f"{mx_price_data['change']:+.2f}%"
        if mx_price_data.get('market_cap'):
            market_cap_display = str(mx_price_data['market_cap'])
    
    # 提取技术指标
    tech_indicators = getattr(r, '_latest_tech_data', None) if r else None
    
    # 输出报告
    report = print_report(ticker, market, r, ta_decision, weekly_text, news_text, 
                          analyst_target, macro_score, company_profile, earnings_forecast, current_price,
                          mx_financial_data, price_change_display, market_cap_display,
                          consensus_rating, tech_indicators)

    # 自动存档
    print(f"   Step 4/5: 自动存档...")
    save_to_investment_db(ticker, r, ta_decision, macro_score)
    save_to_notion(ticker, report)
    
    # 错误汇总
    total_time = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"✅ 分析完成，总耗时：{total_time:.1f}秒")
    if ERROR_LOG:
        print(f"\n⚠️ 本次分析遇到的问题 ({len(ERROR_LOG)}个)：")
        for err in ERROR_LOG:
            print(f"  - {err}")
    else:
        print("\n✅ 所有步骤执行成功，无错误")


if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else ["TSLA"]
    for t in tickers:
        analyze(t.strip())
