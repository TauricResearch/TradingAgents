"""
TradingAgents Discord Bot
- 슬래시 명령: /분석, /대형주, /잔고, /매수, /매도, /상태, /봇정보, /스코어링, /스코어규칙, /수익, /수익초기화
- 대형주+ETF 워치리스트 자동매매 / 손절·익절 감시
- 한국투자증권 API 연동 매매
"""

import os
import asyncio
import datetime
import re
from pathlib import Path
from io import BytesIO
from zoneinfo import ZoneInfo

import discord
import yfinance as yf
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from kis_client import KISClient, format_krw, format_usd
from trade_history import (
    record_trade,
    record_pnl,
    get_total_pnl,
    get_total_pnl_by_currency,
    get_recent_pnl,
    get_ticker_summary,
    reset_pnl_history,
    is_action_done, mark_action_done, get_daily_state,
    ensure_budget_anchor,
    get_budget_anchor,
)

load_dotenv()

# ─── Version ───────────────────────────────────────────────────
BOT_VERSION = "2.2.0"

# ─── Config ────────────────────────────────────────────────────
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN이 .env에 설정되어 있지 않습니다.")

# 봇이 동작할 채널 ID (쉼표로 여러 개 지정 가능, 비워두면 모든 채널에서 동작)
# 예: DISCORD_CHANNEL_IDS=123456789012345678,987654321098765432
_channel_ids_raw = os.getenv("DISCORD_CHANNEL_IDS", "")
ALLOWED_CHANNEL_IDS: set[int] = {
    int(cid.strip()) for cid in _channel_ids_raw.split(",") if cid.strip()
}


def _parse_budget_ratio(env_name: str, default: str = "1.0") -> float:
    """0~1 또는 0~100(%) 형식의 비율 값을 정규화한다."""
    raw = os.getenv(env_name, default).strip()
    if raw.endswith("%"):
        raw = raw[:-1].strip()

    try:
        ratio = float(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{env_name} 값이 올바르지 않습니다. 예: 0.5 또는 50%"
        ) from exc

    if ratio > 1.0:
        ratio /= 100.0

    if not (0.0 < ratio <= 1.0):
        raise RuntimeError(f"{env_name} 값은 0보다 크고 1 이하(또는 100% 이하)여야 합니다.")
    return ratio


def _is_allowed_channel(channel_id: int | None) -> bool:
    """채널 제한이 설정되어 있으면 허용된 채널인지 확인."""
    if channel_id is None:
        return False
    if not ALLOWED_CHANNEL_IDS:
        return True  # 설정 안 하면 모든 채널 허용
    return channel_id in ALLOWED_CHANNEL_IDS

# 손절/익절 임계값 (%)
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "-5.0"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "10.0"))
MONITOR_INTERVAL_MIN = int(os.getenv("MONITOR_INTERVAL_MIN", "30"))

# 데이 트레이딩 설정
DAY_TRADE_PICKS = int(os.getenv("DAY_TRADE_PICKS", "5"))  # 매일 매수할 종목 수
AUTO_BUY_TIME = os.getenv("AUTO_BUY_TIME", "09:30")         # 자동 매수 시각 (HH:MM)
AUTO_SELL_TIME = os.getenv("AUTO_SELL_TIME", "15:20")        # 자동 매도 시각 (HH:MM)
AUTO_BUY_BUDGET_RATIO = _parse_budget_ratio("AUTO_BUY_BUDGET_RATIO", "1.0")
_buy_h, _buy_m = (int(x) for x in AUTO_BUY_TIME.split(":"))
_sell_h, _sell_m = (int(x) for x in AUTO_SELL_TIME.split(":"))

# 미국 데이 트레이딩 설정
ENABLE_US_TRADING = os.getenv("ENABLE_US_TRADING", "false").lower() == "true"
US_DAY_TRADE_PICKS = int(os.getenv("US_DAY_TRADE_PICKS", "5"))
US_AUTO_BUY_TIME = os.getenv("US_AUTO_BUY_TIME", "09:35")
US_AUTO_SELL_TIME = os.getenv("US_AUTO_SELL_TIME", "15:50")
US_AUTO_BUY_BUDGET_RATIO = _parse_budget_ratio(
    "US_AUTO_BUY_BUDGET_RATIO",
    os.getenv("AUTO_BUY_BUDGET_RATIO", "1.0"),
)
_us_buy_h, _us_buy_m = (int(x) for x in US_AUTO_BUY_TIME.split(":"))
_us_sell_h, _us_sell_m = (int(x) for x in US_AUTO_SELL_TIME.split(":"))

config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = os.getenv("DEEP_THINK_LLM", "gemini-3-flash-preview")
config["quick_think_llm"] = os.getenv("QUICK_THINK_LLM", "gemini-3-flash-preview")
config["max_debate_rounds"] = int(os.getenv("MAX_DEBATE_ROUNDS", "1"))
config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "yfinance",
    "news_data": "yfinance",
}


# ─── Bot Setup ─────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

_analysis_lock = asyncio.Lock()

# ─── KIS 클라이언트 초기화 ──────────────────────────────────
kis = KISClient()
KST = ZoneInfo("Asia/Seoul")
NY_TZ = ZoneInfo("America/New_York")
TICKER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "reports"))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
AUTO_REPORT_UPLOAD = os.getenv("AUTO_REPORT_UPLOAD", "true").lower() == "true"
_analysis_symbol_cache: dict[str, str] = {}


def _log(level: str, event: str, message: str):
    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] [{level}] [{event}] {message}")


def _interaction_actor(interaction: discord.Interaction) -> str:
    user = interaction.user
    user_label = str(user) if user else "unknown"
    return f"user={user_label} channel={interaction.channel_id}"


def _latest_yf_close(symbol: str) -> float:
    """yfinance 심볼의 최근 종가 조회 (실패 시 0)."""
    try:
        hist = yf.Ticker(symbol).history(period="7d", interval="1d")
        if hist.empty or "Close" not in hist.columns:
            return 0.0
        close = hist["Close"].dropna()
        if close.empty:
            return 0.0
        return float(close.iloc[-1])
    except Exception:
        return 0.0


def _resolve_analysis_symbol(
    ticker: str,
    market: str | None = None,
    reference_price: float | None = None,
) -> str:
    """분석용 심볼 정규화.

    - US: 티커 그대로 사용
    - KR 6자리: .KS/.KQ 중 yfinance 데이터/가격 근접도로 자동 판별
    """
    t = (ticker or "").upper().strip()
    m = (market or kis.detect_market(t)).upper()
    if m != "KR":
        return t
    if t.endswith((".KS", ".KQ")):
        return t
    if not (t.isdigit() and len(t) == 6):
        return t

    if t in _analysis_symbol_cache:
        return _analysis_symbol_cache[t]

    ref = float(reference_price or 0)
    if ref <= 0 and kis.is_configured:
        try:
            ref = float(kis.get_price(t, market="KR"))
        except Exception:
            ref = 0.0

    candidates = [f"{t}.KS", f"{t}.KQ"]
    prices = {sym: _latest_yf_close(sym) for sym in candidates}
    available = {sym: px for sym, px in prices.items() if px > 0}

    if not available:
        resolved = f"{t}.KS"
    elif len(available) == 1:
        resolved = next(iter(available))
    elif ref > 0:
        resolved = min(
            available.keys(),
            key=lambda sym: abs(available[sym] - ref) / max(ref, 1.0),
        )
    else:
        resolved = max(available.keys(), key=lambda sym: available[sym])

    _analysis_symbol_cache[t] = resolved
    if resolved != f"{t}.KS":
        _log("INFO", "ANALYSIS_SYMBOL_RESOLVED", f"ticker={t} resolved={resolved}")
    return resolved


def _yf_ticker(ticker: str, reference_price: float | None = None) -> str:
    """TradingAgents에 전달할 yfinance 심볼 반환."""
    t = (ticker or "").upper().strip()
    market = kis.detect_market(t)
    if market == "KR":
        return _resolve_analysis_symbol(t, market="KR", reference_price=reference_price)
    return t


def _market_of_ticker(ticker: str) -> str:
    return kis.detect_market(ticker)


def _currency_of_market(market: str) -> str:
    return "USD" if market == "US" else "KRW"


def _format_money(amount: float, currency: str) -> str:
    if currency == "USD":
        return format_usd(amount)
    return f"{amount:,.0f}원"


def _save_report_markdown(
    report_text: str,
    *,
    market: str,
    ticker: str,
    trade_date: str,
    scope: str,
) -> Path:
    """분석 보고서를 reports 디렉터리에 저장."""
    safe_market = re.sub(r"[^A-Z0-9_-]", "_", (market or "NA").upper())
    safe_ticker = re.sub(r"[^A-Z0-9._-]", "_", (ticker or "UNKNOWN").upper())
    safe_scope = re.sub(r"[^A-Z0-9_-]", "_", (scope or "analysis").upper())
    stamp = datetime.datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    filename = f"{stamp}_{safe_scope}_{safe_market}_{safe_ticker}_{trade_date}.md"
    path = REPORTS_DIR / filename
    path.write_text(report_text, encoding="utf-8")
    _log("INFO", "REPORT_SAVED", f"path={path}")
    return path


def _prepare_report_attachment(
    report_text: str,
    *,
    market: str,
    ticker: str,
    trade_date: str,
    scope: str,
) -> tuple[discord.File, Path | None]:
    """디스코드 업로드용 파일 객체와 (가능하면) 로컬 저장 경로를 반환."""
    try:
        saved_path = _save_report_markdown(
            report_text,
            market=market,
            ticker=ticker,
            trade_date=trade_date,
            scope=scope,
        )
        return discord.File(str(saved_path), filename=saved_path.name), saved_path
    except Exception as e:
        _log(
            "ERROR",
            "REPORT_SAVE_FAIL",
            f"scope={scope} market={market} ticker={ticker} error={str(e)[:160]}",
        )
        fallback_name = (
            f"{scope}_{market}_{re.sub(r'[^A-Z0-9._-]', '_', ticker.upper())}_{trade_date}.md"
        )
        return discord.File(fp=BytesIO(report_text.encode("utf-8")), filename=fallback_name), None


def _parse_trade_date(date_text: str | None) -> str:
    """사용자 입력 날짜를 YYYY-MM-DD로 정규화."""
    if not date_text:
        return str(datetime.date.today())
    try:
        parsed = datetime.datetime.strptime(date_text.strip(), "%Y-%m-%d").date()
        return parsed.isoformat()
    except ValueError as exc:
        raise ValueError("날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식으로 입력하세요.") from exc


def _validate_ticker_format(ticker: str) -> str | None:
    """티커 문자열 형식 검증."""
    if not ticker:
        return "티커를 입력해주세요."
    if not TICKER_PATTERN.fullmatch(ticker):
        return "티커 형식이 올바르지 않습니다. 예: AAPL, BRK-B, 005930"
    return None


def _ticker_has_market_data(ticker: str) -> bool:
    """실제 종목 데이터가 존재하는지 확인."""
    market = _market_of_ticker(ticker)
    kr_price = 0.0

    # 한국 6자리 종목은 KIS 시세를 우선 확인
    if market == "KR" and kis.is_configured:
        try:
            kr_price = float(kis.get_price(ticker, market="KR"))
            if kr_price <= 0:
                return False
        except Exception as e:
            _log("WARN", "TICKER_VALIDATE_KIS_FAIL", f"ticker={ticker} error={str(e)[:160]}")

    # 글로벌 티커 포함 yfinance로 최종 확인
    try:
        yf_symbol = _yf_ticker(ticker, reference_price=kr_price if market == "KR" else None)
        hist = yf.Ticker(yf_symbol).history(period="1mo", interval="1d")
        if hist.empty or "Close" not in hist.columns:
            return False
        return not hist["Close"].dropna().empty
    except Exception:
        return False


async def _validate_analysis_ticker(ticker: str) -> tuple[bool, str]:
    """분석 요청 전에 티커 유효성 검증."""
    format_error = _validate_ticker_format(ticker)
    if format_error:
        return False, format_error

    loop = asyncio.get_running_loop()
    has_data = await loop.run_in_executor(None, _ticker_has_market_data, ticker)
    if not has_data:
        return (
            False,
            f"`{ticker}` 종목 데이터를 찾지 못했습니다. "
            "오타 여부와 거래소 접미사(예: 005930, AAPL, 7203.T)를 확인해주세요.",
        )
    return True, ""


def _is_market_day(market: str = "KR") -> bool:
    """시장 거래일 여부 확인."""
    market = market.upper()
    now = datetime.datetime.now(NY_TZ if market == "US" else KST).date()
    if market == "US":
        return kis.is_market_open(now, market="US")

    if now.weekday() >= 5:
        return False
    if kis.is_configured:
        return kis.is_market_open(now, market="KR")
    return True


def _is_market_open_now(market: str = "KR") -> bool:
    """시장 정규장 시간 여부 확인."""
    return kis.is_market_open_now(market=market.upper())


def _market_open_context(market: str = "KR") -> tuple[ZoneInfo, datetime.time, str, str]:
    """시장별 정규장 시작 시각과 표시용 타임존 라벨."""
    market = market.upper()
    if market == "US":
        return NY_TZ, datetime.time(9, 30), "09:30", "ET"
    return KST, datetime.time(9, 0), "09:00", "KST"


def _is_before_market_open(market: str = "KR") -> bool:
    """시장 개장 전인지 확인."""
    tz, open_time, _, _ = _market_open_context(market)
    now = datetime.datetime.now(tz)
    return now.time() < open_time


async def _wait_for_market_open(
    channel: discord.abc.Messageable,
    market: str = "KR",
) -> bool:
    """개장 전이면 개장까지 대기하고, 장 마감 후면 False를 반환."""
    market = market.upper()
    if _is_market_open_now(market):
        return True
    if not _is_before_market_open(market):
        return False

    _, _, open_label, _ = _market_open_context(market)
    market_label = "미국 장" if market == "US" else "장"
    await channel.send(f"⏳ {market_label}이 아직 열리지 않았습니다. {open_label} 개장까지 대기 중…")
    _log("INFO", f"{market}_AUTO_BUY_WAIT_MARKET", "장 전 분석 완료, 개장 대기")
    while not _is_market_open_now(market):
        await asyncio.sleep(10)
    await channel.send("🔔 **장이 열렸습니다!** 매수 주문을 진행합니다.")
    _log("INFO", f"{market}_AUTO_BUY_MARKET_OPENED", "개장 확인, 매수 진행")
    return True


def _resolve_scoring_watchlist(
    configured_watchlist: list[str],
    cap_rank: list[dict],
    volume_rank: list[dict],
    *,
    market: str,
) -> list[str]:
    """워치리스트 미설정 시 공식 랭킹 결과로 후보 풀을 보완한다."""
    market = market.upper()
    if configured_watchlist:
        return configured_watchlist

    prefix = "US_" if market == "US" else ""
    watchlist_name = f"{market}_WATCHLIST"
    if cap_rank:
        watchlist = [item["ticker"] for item in cap_rank]
        _log("INFO", f"{prefix}SCORING_FALLBACK_CAP", f"{watchlist_name} 미설정 → 시총 TOP{len(watchlist)} 사용")
        return watchlist
    if volume_rank:
        watchlist = [item["ticker"] for item in volume_rank]
        _log(
            "INFO",
            f"{prefix}SCORING_FALLBACK_VOLUME",
            f"{watchlist_name} 미설정 → 거래량 TOP{len(watchlist)} 사용",
        )
        return watchlist

    reason = f"{watchlist_name} 미설정 + 시총/거래량 조회 실패"
    _log("WARN", f"{prefix}SCORING_NO_CANDIDATES", reason)
    return []


def _auto_buy_budget_ratio(market: str = "KR") -> float:
    return US_AUTO_BUY_BUDGET_RATIO if market.upper() == "US" else AUTO_BUY_BUDGET_RATIO


def _compute_auto_buy_budget(market: str, available_cash: float) -> dict[str, float]:
    """자동매수에 사용할 오늘 예산을 계산한다.

    - 기준 자금(anchor): 시장별로 저장되는 최대 확인 예수금
    - 일일 예산: anchor × 설정 비율
    - 실제 사용 가능 예산: min(현재 예수금, 일일 예산)
    """
    market = market.upper()
    cash = max(float(available_cash), 0.0)
    ratio = _auto_buy_budget_ratio(market)
    anchor = ensure_budget_anchor(market, cash) if cash > 0 else get_budget_anchor(market)
    anchor = max(float(anchor), cash)
    target_budget = anchor * ratio if anchor > 0 else cash * ratio
    usable_budget = min(cash, target_budget) if cash > 0 else 0.0

    return {
        "market": market,
        "available_cash": cash,
        "anchor": anchor,
        "ratio": ratio,
        "target_budget": target_budget,
        "usable_budget": usable_budget,
    }


# ─── Helper: 보고서 생성 ──────────────────────────────────────
def _build_report_text(
    final_state: dict,
    ticker: str,
    *,
    market: str | None = None,
    analysis_symbol: str | None = None,
) -> str:
    """final_state에서 Markdown 보고서 텍스트 생성."""
    sections: list[str] = []

    analyst_parts = []
    if final_state.get("market_report"):
        analyst_parts.append(("📊 시장 애널리스트", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        analyst_parts.append(("💬 소셜 미디어 애널리스트", final_state["sentiment_report"]))
    if final_state.get("news_report"):
        analyst_parts.append(("📰 뉴스 애널리스트", final_state["news_report"]))
    if final_state.get("fundamentals_report"):
        analyst_parts.append(("📈 펀더멘털 애널리스트", final_state["fundamentals_report"]))
    if analyst_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in analyst_parts)
        sections.append(f"## I. 애널리스트팀 보고서\n\n{content}")

    if final_state.get("investment_debate_state"):
        debate = final_state["investment_debate_state"]
        research_parts = []
        if debate.get("bull_history"):
            research_parts.append(("🟢 강세 애널리스트", debate["bull_history"]))
        if debate.get("bear_history"):
            research_parts.append(("🔴 약세 애널리스트", debate["bear_history"]))
        if debate.get("judge_decision"):
            research_parts.append(("⚖️ 리서치 매니저", debate["judge_decision"]))
        if research_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in research_parts)
            sections.append(f"## II. 리서치팀 판단\n\n{content}")

    if final_state.get("trader_investment_plan"):
        sections.append(
            f"## III. 트레이딩팀 계획\n\n### 🏦 트레이더\n{final_state['trader_investment_plan']}"
        )

    if final_state.get("risk_debate_state"):
        risk = final_state["risk_debate_state"]
        risk_parts = []
        if risk.get("aggressive_history"):
            risk_parts.append(("🔥 공격적 애널리스트", risk["aggressive_history"]))
        if risk.get("conservative_history"):
            risk_parts.append(("🛡️ 보수적 애널리스트", risk["conservative_history"]))
        if risk.get("neutral_history"):
            risk_parts.append(("⚖️ 중립적 애널리스트", risk["neutral_history"]))
        if risk_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in risk_parts)
            sections.append(f"## IV. 리스크 관리팀 결정\n\n{content}")

        if risk.get("judge_decision"):
            sections.append(
                f"## V. 포트폴리오 매니저 결정\n\n### 💼 포트폴리오 매니저\n{risk['judge_decision']}"
            )

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_lines = [f"# 📋 트레이딩 분석 보고서: {ticker}", "", f"생성일시: {now}"]
    if market:
        header_lines.append(f"시장: {market}")
    if analysis_symbol and analysis_symbol.upper() != ticker.upper():
        header_lines.append(f"분석 심볼: {analysis_symbol}")
    header = "\n".join(header_lines) + "\n\n"
    return header + "\n\n".join(sections)


def _extract_decision_summary(
    final_state: dict,
    decision: str,
    ticker: str,
    market: str | None = None,
) -> str:
    """Discord Embed에 넣을 요약 문자열 생성."""
    market = (market or _market_of_ticker(ticker)).upper()
    lines = [f"**시장:** {market}", f"**종목:** {ticker}", f"**최종 결정:** {decision}"]
    if final_state.get("investment_plan"):
        plan = final_state["investment_plan"]
        if len(plan) > 300:
            plan = plan[:300] + "…"
        lines.append(f"**투자 계획 요약:**\n{plan}")
    return "\n".join(lines)


async def _show_trade_button(
    channel: discord.abc.Messageable,
    ticker: str,
    decision: str,
    market: str | None = None,
):
    """개별 분석 결과에 따라 BUY/SELL 확인 버튼을 표시한다."""
    if not kis.is_configured:
        return

    market = (market or _market_of_ticker(ticker)).upper()
    currency = _currency_of_market(market)
    if market == "US" and not kis.enable_us_trading:
        await channel.send(
            "ℹ️ 미국 자동주문은 비활성화되어 있습니다. `.env`의 "
            "`ENABLE_US_TRADING=true` 설정 후 사용하세요."
        )
        return
    mode_label = "🧪 모의투자" if kis.virtual else "💰 실전투자"
    loop = asyncio.get_running_loop()

    if decision.upper() == "BUY":
        if not _is_market_open_now(market):
            _log("INFO", "MANUAL_BUY_BLOCKED", f"market={market} ticker={ticker}")
            await channel.send(
                f"ℹ️ `{ticker}`({market}) BUY 신호이지만 현재 장외/휴장이라 "
                "수동 매수 버튼을 표시하지 않습니다."
            )
            return
        try:
            price = await loop.run_in_executor(None, kis.get_price, ticker, market)
            if price <= 0:
                return
            budget = kis.us_max_order_amount if market == "US" else kis.max_order_amount
            qty = int(budget // price)
            if qty <= 0:
                await channel.send(
                    f"⚠️ {ticker} — 예산({_format_money(budget, currency)}) 대비 "
                    f"현재가({_format_money(price, currency)})가 높아 매수 불가"
                )
                return
            view = BuyConfirmView(
                ticker=ticker,
                name=ticker,
                qty=qty,
                price=price,
                market=market,
                currency=currency,
            )
            embed = discord.Embed(
                title=f"🛒 {ticker} 매수 확인",
                description=(
                    f"**시장:** {market}\n"
                    f"**종목:** `{ticker}`\n"
                    f"**현재가:** {_format_money(price, currency)}\n"
                    f"**매수 수량:** {qty}주\n"
                    f"**예상 금액:** {_format_money(qty * price, currency)}\n\n"
                    f"매수하시겠습니까?"
                ),
                color=0x00FF00,
            )
            embed.set_footer(text=f"{mode_label} | {currency}")
            await channel.send(embed=embed, view=view)
        except Exception:
            pass

    elif decision.upper() == "SELL":
        try:
            balance_data = await loop.run_in_executor(None, kis.get_balance, market)
            holding = next(
                (
                    h for h in balance_data["holdings"]
                    if h["ticker"] == ticker and h.get("market", market) == market
                ),
                None,
            )
            if not holding or holding["qty"] <= 0:
                return
            view = SellConfirmView(
                ticker=ticker,
                name=holding["name"],
                qty=holding["qty"],
                avg_price=holding["avg_price"],
                market=market,
                currency=currency,
                exchange=holding.get("exchange", ""),
            )
            embed = discord.Embed(
                title=f"🔴 {holding['name']} 매도 확인",
                description=(
                    f"**시장:** {market}\n"
                    f"**종목:** {holding['name']} (`{ticker}`)\n"
                    f"**보유:** {holding['qty']}주 "
                    f"(평균 {_format_money(holding['avg_price'], currency)})\n"
                    f"**현재가:** {_format_money(holding['current_price'], currency)}\n"
                    f"**손익:** {_format_money(holding['pnl'], currency)} "
                    f"({holding['pnl_rate']:+.2f}%)\n\n"
                    f"AI가 SELL을 권고합니다. 전량 매도하시겠습니까?"
                ),
                color=0xFF0000,
            )
            embed.set_footer(text=f"{mode_label} | {currency}")
            await channel.send(embed=embed, view=view)
        except Exception:
            pass


# ─── Helper: 대형주+ETF 워치리스트 스코어링 ─────────────────
async def _compute_stock_scores(count: int = 10) -> list[dict]:
    """
    KR_WATCHLIST(대형주+ETF) 기반 스코어링.

    후보 풀: .env의 KR_WATCHLIST에 등록된 종목만 사용
    스코어링 기준:
      - 워치리스트 기본 점수: +30 (대형주/ETF 신뢰 보너스)
      - 등락률 0%<x≤2%: +25 (안정적 상승)
      - 등락률 2%<x≤5%: +15
      - 시가총액 top30 진입 시: +10
      - 거래량 top30 진입 시: +5

    필터: 등락률 >8% 또는 <-5% → 제외 (대형주에는 여유롭게)

    Returns:
        [{"ticker", "name", "price", "score", "signals": [str]}, ...] 점수 내림차순
    """
    loop = asyncio.get_running_loop()

    # 보조 데이터: 시총/거래량 랭킹 (가능하면 조회)
    try:
        cap_list = await loop.run_in_executor(None, kis.get_top_market_cap, 30)
    except Exception:
        cap_list = []
    try:
        volume_list = await loop.run_in_executor(None, kis.get_volume_rank, 30)
    except Exception:
        volume_list = []

    watchlist = _resolve_scoring_watchlist(
        kis.kr_watchlist,
        cap_list,
        volume_list,
        market="KR",
    )
    if not watchlist:
        return []

    cap_map = {s["ticker"]: s for s in cap_list}
    volume_map = {s["ticker"]: s for s in volume_list}

    scored: list[dict] = []
    for ticker in watchlist:
        try:
            price = await loop.run_in_executor(None, kis.get_price, ticker, "KR")
        except Exception:
            price = 0
        if price <= 0:
            continue

        # yfinance로 전일 대비 등락률 계산
        yf_sym = _yf_ticker(ticker, reference_price=price)
        try:
            hist = await loop.run_in_executor(
                None,
                lambda sym=yf_sym: yf.Ticker(sym).history(period="5d", interval="1d"),
            )
            closes = hist["Close"].dropna() if not hist.empty and "Close" in hist.columns else None
            if closes is not None and len(closes) >= 2:
                prev = float(closes.iloc[-2])
                prdy_ctrt = (price - prev) / prev * 100 if prev > 0 else 0.0
            else:
                prdy_ctrt = 0.0
        except Exception:
            prdy_ctrt = 0.0

        # 필터: 급등/급락 제외
        if prdy_ctrt > 8.0 or prdy_ctrt < -5.0:
            continue

        score = 30  # 워치리스트 기본 점수 (대형주/ETF 신뢰)
        signals: list[str] = ["워치리스트"]

        # 등락률 시그널
        if 0 < prdy_ctrt <= 2:
            score += 25
            signals.append(f"등락률 +{prdy_ctrt:.1f}%(안정상승)")
        elif 2 < prdy_ctrt <= 5:
            score += 15
            signals.append(f"등락률 +{prdy_ctrt:.1f}%")

        # 시가총액 랭킹 보너스
        if ticker in cap_map:
            score += 10
            signals.append(f"시총 {cap_map[ticker]['rank']}위")

        # 거래량 랭킹 보너스
        if ticker in volume_map:
            score += 5
            signals.append(f"거래량 {volume_map[ticker]['rank']}위")

        # 이름 조회: 랭킹 데이터에 있으면 가져오고, 없으면 티커 사용
        name = ""
        for m in (cap_map, volume_map):
            if ticker in m:
                name = m[ticker].get("name", "")
                break
        if not name:
            name = ticker

        scored.append({
            "ticker": ticker,
            "name": name,
            "price": price,
            "prdy_ctrt": prdy_ctrt,
            "score": score,
            "signals": signals,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:count]


def _compute_us_scores_from_yfinance(
    watchlist: list[str],
    count: int = 10,
    cap_map: dict[str, dict] | None = None,
    volume_map: dict[str, dict] | None = None,
) -> list[dict]:
    """US_WATCHLIST(대형주+ETF) 기반 스코어링."""
    cap_map = cap_map or {}
    volume_map = volume_map or {}
    scored: list[dict] = []
    for ticker in watchlist:
        try:
            hist = yf.Ticker(ticker).history(period="5d", interval="1d")
            if hist.empty or "Close" not in hist.columns:
                continue
            closes = hist["Close"].dropna()
            if len(closes) < 2:
                continue

            prev = float(closes.iloc[-2])
            if prev <= 0:
                continue

            price = 0.0
            if kis.enable_us_trading and kis.is_configured:
                try:
                    price = float(kis.get_price(ticker, "US"))
                except Exception:
                    price = 0.0
            if price <= 0:
                price = float(closes.iloc[-1])

            pct = (price - prev) / prev * 100

            if pct > 8.0 or pct < -5.0:
                continue

            score = 30
            signals: list[str] = ["워치리스트"]
            if 0 < pct <= 2:
                score += 25
                signals.append(f"등락률 +{pct:.1f}%(안정상승)")
            elif 2 < pct <= 5:
                score += 15
                signals.append(f"등락률 +{pct:.1f}%")

            cap_info = cap_map.get(ticker)
            if cap_info:
                score += 10
                signals.append(f"시총 {cap_info.get('rank', 0)}위")

            volume_info = volume_map.get(ticker)
            if volume_info:
                score += 5
                signals.append(f"거래량 {volume_info.get('rank', 0)}위")

            scored.append(
                {
                    "market": "US",
                    "currency": "USD",
                    "exchange": (volume_info or {}).get(
                        "exchange",
                        (cap_info or {}).get(
                            "exchange",
                            kis._us_exchange_cache.get(ticker, ""),
                        ),
                    ),
                    "ticker": ticker,
                    "name": (cap_info or {}).get(
                        "name",
                        (volume_info or {}).get("name", ticker),
                    ),
                    "price": price,
                    "prdy_ctrt": pct,
                    "score": score,
                    "signals": signals,
                }
            )
        except Exception:
            continue

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:count]


async def _compute_us_stock_scores(count: int = 10) -> list[dict]:
    """US_WATCHLIST(대형주+ETF) 기반 미국 후보 스코어링."""
    loop = asyncio.get_running_loop()

    cap_rank: list[dict] = []
    volume_rank: list[dict] = []
    if kis.enable_us_trading and kis.is_configured:
        try:
            cap_rank = await loop.run_in_executor(None, kis.get_us_market_cap_rank, 30)
        except Exception:
            cap_rank = []
        try:
            volume_rank = await loop.run_in_executor(None, kis.get_us_volume_rank, 30)
        except Exception:
            volume_rank = []

    watchlist = _resolve_scoring_watchlist(
        kis.us_watchlist,
        cap_rank,
        volume_rank,
        market="US",
    )
    if not watchlist:
        return []

    cap_map = {item["ticker"]: item for item in cap_rank}
    volume_map = {item["ticker"]: item for item in volume_rank}
    return await loop.run_in_executor(
        None,
        _compute_us_scores_from_yfinance,
        watchlist,
        count,
        cap_map,
        volume_map,
    )


# ─── Helper: TOP5 분석 실행 ───────────────────────────────────
async def _run_top5_analysis(channel: discord.abc.Messageable, trade_date: str):
    """스코어링 TOP5를 조회하고 각각 AI 분석 실행."""
    status = await channel.send("📊 **스코어링 TOP5** 조회 중…")
    loop = asyncio.get_running_loop()
    top5 = await _compute_stock_scores(count=5)

    if not top5:
        await status.edit(content="❌ 스코어링 후보가 없습니다. (휴장일?)")
        return

    # TOP5 목록 Embed
    desc_lines = []
    for i, s in enumerate(top5, 1):
        sig_str = ", ".join(s.get("signals", []))
        desc_lines.append(
            f"**{i}.** {s['name']} (`{s['ticker']}`) "
            f"— {s['price']:,}원 | **{s['score']}점** | {sig_str}"
        )
    list_embed = discord.Embed(
        title=f"🏆 스코어링 TOP {len(top5)}",
        description="\n".join(desc_lines),
        color=0x0066FF,
        timestamp=datetime.datetime.now(),
    )
    mode_label = "🧪 모의투자" if kis.virtual else "💰 실전투자"
    list_embed.set_footer(text=f"TradingAgents | {mode_label}")
    await status.edit(content=None, embed=list_embed)

    # 각 종목 AI 분석
    buy_targets = []
    sell_targets = []
    total = len(top5)
    for i, stock_info in enumerate(top5):
        ticker = stock_info["ticker"]
        name = stock_info["name"]
        progress = await channel.send(
            f"🔍 [{i+1}/{total}] **{name}** (`{ticker}`) 분석 중… (약 2~5분)"
        )
        try:
            ta = TradingAgentsGraph(debug=False, config=config)
            analysis_symbol = _yf_ticker(ticker, reference_price=stock_info["price"])
            final_state, decision = await loop.run_in_executor(
                None, ta.propagate, analysis_symbol, trade_date
            )

            color_map = {"BUY": 0x00FF00, "SELL": 0xFF0000, "HOLD": 0xFFAA00}
            summary = _extract_decision_summary(final_state, decision, ticker)
            emoji = "🟢" if decision == "BUY" else "🔴" if decision == "SELL" else "🟡"
            embed = discord.Embed(
                title=f"{emoji} {name} ({ticker}) → {decision}",
                description=summary,
                color=color_map.get(decision.upper(), 0x808080),
            )
            await progress.edit(content=None, embed=embed)

            report_text = _build_report_text(
                final_state,
                ticker,
                market="KR",
                analysis_symbol=analysis_symbol,
            )
            report_file, report_path = _prepare_report_attachment(
                report_text,
                market="KR",
                ticker=ticker,
                trade_date=trade_date,
                scope="TOP5",
            )
            if AUTO_REPORT_UPLOAD:
                try:
                    await channel.send(file=report_file)
                except Exception as e:
                    _log(
                        "WARN",
                        "TOP5_REPORT_UPLOAD_FAIL",
                        f"ticker={ticker} error={str(e)[:160]} path={report_path or 'N/A'}",
                    )
                    await channel.send(
                        "⚠️ 보고서 파일 업로드에 실패했습니다. "
                        + (f"로컬 저장 파일: `{report_path}`" if report_path else "로컬 저장도 실패했습니다.")
                    )

            if decision.upper() == "BUY":
                buy_targets.append({
                    "ticker": ticker,
                    "name": name,
                    "price": stock_info["price"],
                })
            elif decision.upper() == "SELL":
                sell_targets.append({
                    "ticker": ticker,
                    "name": name,
                })
        except Exception as e:
            await progress.edit(
                content=f"❌ {name} ({ticker}) 분석 실패: {str(e)[:200]}"
            )

    # ── SELL 종목: 보유 중이면 매도 버튼 표시 ──────────────────
    if sell_targets and kis.is_configured:
        try:
            loop = asyncio.get_running_loop()
            balance_data = await loop.run_in_executor(None, kis.get_balance, "KR")
            holdings_map = {h["ticker"]: h for h in balance_data["holdings"]}
        except Exception:
            holdings_map = {}

        for target in sell_targets:
            holding = holdings_map.get(target["ticker"])
            if holding and holding["qty"] > 0:
                view = SellConfirmView(
                    ticker=target["ticker"],
                    name=target["name"],
                    qty=holding["qty"],
                    avg_price=holding["avg_price"],
                    market="KR",
                    currency="KRW",
                    exchange=holding.get("exchange", "KRX"),
                )
                embed = discord.Embed(
                    title=f"🔴 {target['name']} 매도 확인",
                    description=(
                        f"**종목:** {target['name']} (`{target['ticker']}`)\n"
                        f"**보유:** {holding['qty']}주 (평균 {_format_money(holding['avg_price'], 'KRW')})\n"
                        f"**현재가:** {_format_money(holding['current_price'], 'KRW')}\n"
                        f"**손익:** {_format_money(holding['pnl'], 'KRW')} ({holding['pnl_rate']:+.2f}%)\n\n"
                        f"AI가 SELL을 권고합니다. 전량 매도하시겠습니까?"
                    ),
                    color=0xFF0000,
                )
                embed.set_footer(text=mode_label)
                await channel.send(embed=embed, view=view)

    # ── BUY 종목: 매수 버튼 표시 ──────────────────────────────
    if not buy_targets and not sell_targets:
        await channel.send("📋 **분석 완료** — BUY/SELL 추천 종목이 없습니다. 모두 HOLD입니다.")
        return
    elif not buy_targets:
        await channel.send("📋 **분석 완료** — BUY 추천 종목이 없습니다.")
        return

    if not kis.is_configured:
        buy_list = ", ".join(f"{t['name']}" for t in buy_targets)
        await channel.send(
            f"📋 **분석 완료** — BUY 추천: {buy_list}\n"
            f"⚠️ KIS API가 설정되지 않아 자동 매매를 사용할 수 없습니다."
        )
        return

    if not _is_market_open_now("KR"):
        buy_list = ", ".join(f"{t['name']}({t['ticker']})" for t in buy_targets)
        await channel.send(
            "ℹ️ **장외/휴장 상태**라 `/대형주` 수동 매수 버튼을 비활성화했습니다.\n"
            f"추천 BUY 종목: {buy_list}"
        )
        _log("INFO", "TOP5_BUY_BUTTON_BLOCKED", "market closed")
        return

    per_stock_budget = int(kis.max_order_amount // len(buy_targets))
    await channel.send(
        f"🧪 **테스트 모드 예산(수동 /대형주)**\n"
            f"총 상한: {_format_money(kis.max_order_amount, 'KRW')} | "
            f"종목당: {_format_money(per_stock_budget, 'KRW')}"
    )
    for target in buy_targets:
        qty = int(per_stock_budget // target["price"]) if target["price"] > 0 else 0
        if qty <= 0:
            await channel.send(
                f"⚠️ {target['name']} — 예산({_format_money(per_stock_budget, 'KRW')}) 부족으로 매수 불가"
            )
            continue
        view = BuyConfirmView(
            ticker=target["ticker"],
            name=target["name"],
            qty=qty,
            price=target["price"],
            market="KR",
            currency="KRW",
        )
        embed = discord.Embed(
            title=f"🛒 {target['name']} 매수 확인",
            description=(
                f"**종목:** {target['name']} (`{target['ticker']}`)\n"
                f"**현재가:** {_format_money(target['price'], 'KRW')}\n"
                f"**매수 수량:** {qty}주\n"
                f"**예산 규칙:** 수동 /대형주 테스트 상한({_format_money(per_stock_budget, 'KRW')})\n"
                f"**예상 금액:** {_format_money(qty * target['price'], 'KRW')}\n\n"
                f"매수하시겠습니까?"
            ),
            color=0x00FF00,
        )
        embed.set_footer(text=mode_label)
        await channel.send(embed=embed, view=view)


# ─── Discord UI: 매수/매도 확인 버튼 ──────────────────────────
class BuyConfirmView(discord.ui.View):
    """매수 확인/건너뛰기 버튼"""

    def __init__(
        self,
        ticker: str,
        name: str,
        qty: int,
        price: float,
        market: str = "KR",
        currency: str = "KRW",
        reason: str = "AI BUY 신호",
    ):
        super().__init__(timeout=300)
        self.ticker = ticker
        self.name = name
        self.qty = qty
        self.price = float(price)
        self.market = market.upper()
        self.currency = currency.upper()
        self.reason = reason

    @discord.ui.button(label="✅ 매수 확인", style=discord.ButtonStyle.green)
    async def confirm_buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, kis.buy_stock, self.ticker, self.qty, 0, self.market
            )
            if result["success"]:
                record_trade(
                    self.ticker, self.name, "BUY",
                    self.qty, self.price,
                    order_no=result.get("order_no", ""),
                    reason=self.reason,
                    market=self.market,
                    currency=self.currency,
                )
                embed = discord.Embed(
                    title=f"✅ {self.name} 매수 완료",
                    description=(
                        f"**시장:** {self.market}\n"
                        f"**주문번호:** {result['order_no']}\n"
                        f"**수량:** {self.qty}주\n"
                        f"**평균 단가:** {_format_money(self.price, self.currency)}\n"
                        f"**메시지:** {result['message']}"
                    ),
                    color=0x00FF00,
                )
            else:
                embed = discord.Embed(
                    title=f"❌ {self.name} 매수 실패",
                    description=f"**사유:** {result['message']}",
                    color=0xFF0000,
                )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ 매수 오류: {str(e)[:500]}")
        self.stop()

    @discord.ui.button(label="⏭️ 건너뛰기", style=discord.ButtonStyle.grey)
    async def skip_buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"⏭️ {self.name} 매수를 건너뛰었습니다.", ephemeral=True
        )
        self.stop()


class SellConfirmView(discord.ui.View):
    """매도 확인/취소 버튼"""

    def __init__(
        self,
        ticker: str,
        name: str,
        qty: int,
        avg_price: float = 0,
        market: str = "KR",
        currency: str = "KRW",
        exchange: str = "",
    ):
        super().__init__(timeout=120)
        self.ticker = ticker
        self.name = name
        self.qty = qty
        self.avg_price = float(avg_price)  # 평균 매수가 (실현손익 계산용)
        self.market = market.upper()
        self.currency = currency.upper()
        self.exchange = exchange

    @discord.ui.button(label="🔴 매도 확인", style=discord.ButtonStyle.danger)
    async def confirm_sell(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, kis.sell_stock, self.ticker, self.qty, 0, self.market
            )
            if result["success"]:
                # 현재가 조회하여 실현손익 기록
                try:
                    sell_price = await loop.run_in_executor(None, kis.get_price, self.ticker, self.market)
                except Exception:
                    sell_price = 0
                record_trade(
                    self.ticker, self.name, "SELL",
                    self.qty, sell_price,
                    order_no=result.get("order_no", ""),
                    reason="매도",
                    market=self.market,
                    currency=self.currency,
                )
                if self.avg_price > 0 and sell_price > 0:
                    record_pnl(
                        self.ticker,
                        self.name,
                        self.avg_price,
                        sell_price,
                        self.qty,
                        market=self.market,
                        currency=self.currency,
                    )
                embed = discord.Embed(
                    title=f"✅ {self.name} 매도 완료",
                    description=(
                        f"**시장:** {self.market}\n"
                        f"**종목:** `{self.ticker}`\n"
                        f"**수량:** {self.qty}주\n"
                        f"**체결 단가:** {_format_money(sell_price, self.currency)}\n"
                        f"**주문번호:** {result['order_no']}\n"
                        f"**메시지:** {result['message']}"
                    ),
                    color=0x00FF00,
                )
            else:
                embed = discord.Embed(
                    title="❌ 매도 실패",
                    description=f"**사유:** {result['message']}",
                    color=0xFF0000,
                )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ 매도 오류: {str(e)[:500]}")
        self.stop()

    @discord.ui.button(label="취소", style=discord.ButtonStyle.grey)
    async def cancel_sell(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🚫 매도를 취소했습니다.", ephemeral=True)
        self.stop()

# ─── Slash Command: /분석 ──────────────────────────────────────
@tree.command(name="분석", description="멀티 에이전트 AI 투자 분석 보고서를 생성합니다")
@app_commands.describe(
    ticker="분석할 종목 티커 (예: AAPL, MSFT, 005930)",
    date="분석 기준일 (YYYY-MM-DD, 기본: 오늘)",
)
async def analyze(
    interaction: discord.Interaction,
    ticker: str,
    date: str | None = None,
):
    ticker = ticker.upper().strip()
    market = _market_of_ticker(ticker)
    try:
        trade_date = _parse_trade_date(date)
    except ValueError as e:
        await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    _log(
        "INFO",
        "SLASH_ANALYZE_START",
        f"{_interaction_actor(interaction)} market={market} ticker={ticker} date={trade_date}",
    )

    if not _is_allowed_channel(interaction.channel_id):
        _log("WARN", "SLASH_ANALYZE_BLOCKED", f"허용되지 않은 채널 channel={interaction.channel_id}")
        await interaction.followup.send(
            "❌ 이 채널에서는 분석 명령을 사용할 수 없습니다."
        )
        return

    if _analysis_lock.locked():
        _log("WARN", "SLASH_ANALYZE_BUSY", "analysis lock already acquired")
        await interaction.followup.send(
            "⏳ 이미 다른 분석이 진행 중입니다. 잠시 후 다시 시도해주세요."
        )
        return

    is_valid_ticker, ticker_error = await _validate_analysis_ticker(ticker)
    if not is_valid_ticker:
        _log("WARN", "SLASH_ANALYZE_INVALID_TICKER", f"ticker={ticker} reason={ticker_error}")
        await interaction.followup.send(f"❌ {ticker_error}")
        return

    async with _analysis_lock:
        status_msg = await interaction.followup.send(
            f"🔍 **{ticker} ({market})** 분석을 시작합니다… (약 2~5분 소요)\n"
            f"📅 기준일: {trade_date}",
            wait=True,
        )

        try:
            loop = asyncio.get_running_loop()
            ta = TradingAgentsGraph(debug=False, config=config)
            analysis_ref_price = None
            if market == "KR" and kis.is_configured:
                try:
                    analysis_ref_price = await loop.run_in_executor(
                        None, kis.get_price, ticker, "KR"
                    )
                except Exception:
                    analysis_ref_price = None
            analysis_symbol = _yf_ticker(ticker, reference_price=analysis_ref_price)
            final_state, decision = await loop.run_in_executor(
                None, ta.propagate, analysis_symbol, trade_date
            )

            report_text = _build_report_text(
                final_state,
                ticker,
                market=market,
                analysis_symbol=analysis_symbol,
            )
            summary = _extract_decision_summary(final_state, decision, ticker, market)

            color_map = {"BUY": 0x00FF00, "SELL": 0xFF0000, "HOLD": 0xFFAA00}
            embed = discord.Embed(
                title=f"📋 {ticker} ({market}) 분석 완료",
                description=summary,
                color=color_map.get(decision.upper(), 0x808080),
                timestamp=datetime.datetime.now(),
            )
            embed.set_footer(text="TradingAgents 멀티 에이전트 분석")

            await status_msg.edit(content=None, embed=embed)

            report_file, report_path = _prepare_report_attachment(
                report_text,
                market=market,
                ticker=ticker,
                trade_date=trade_date,
                scope="SLASH",
            )
            try:
                await interaction.followup.send(
                    f"📄 **{ticker} ({market})** 전체 보고서:",
                    file=report_file,
                )
            except Exception as e:
                _log(
                    "WARN",
                    "SLASH_ANALYZE_REPORT_UPLOAD_FAIL",
                    f"ticker={ticker} error={str(e)[:160]} path={report_path or 'N/A'}",
                )
                await interaction.followup.send(
                    "⚠️ 보고서 파일 업로드에 실패했습니다. "
                    + (f"로컬 저장 파일: `{report_path}`" if report_path else "로컬 저장도 실패했습니다.")
                )

            # BUY/SELL 판정 시 자동매매 버튼
            ch = interaction.channel
            if isinstance(ch, discord.abc.Messageable):
                await _show_trade_button(ch, ticker, decision, market=market)

            _log(
                "INFO",
                "SLASH_ANALYZE_DONE",
                f"market={market} ticker={ticker} decision={decision}",
            )

        except Exception as e:
            _log("ERROR", "SLASH_ANALYZE_ERROR", f"ticker={ticker} error={str(e)[:200]}")
            await status_msg.edit(
                content=f"❌ 분석 중 오류가 발생했습니다:\n```\n{str(e)[:1500]}\n```"
            )


# ─── Slash Command: /대형주 ─────────────────────────────────────
@tree.command(name="대형주", description="스코어링 TOP5 분석 + 매수 추천")
@app_commands.describe(date="분석 기준일 (YYYY-MM-DD, 기본: 오늘)")
async def top_stocks(interaction: discord.Interaction, date: str | None = None):
    try:
        trade_date = _parse_trade_date(date)
    except ValueError as e:
        await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    _log("INFO", "SLASH_TOP5_START", f"{_interaction_actor(interaction)} date={trade_date}")

    if not _is_allowed_channel(interaction.channel_id):
        _log("WARN", "SLASH_TOP5_BLOCKED", f"허용되지 않은 채널 channel={interaction.channel_id}")
        await interaction.followup.send("❌ 이 채널에서는 사용할 수 없습니다.")
        return

    if _analysis_lock.locked():
        _log("WARN", "SLASH_TOP5_BUSY", "analysis lock already acquired")
        await interaction.followup.send("⏳ 이미 다른 분석이 진행 중입니다.")
        return

    await interaction.followup.send(f"🚀 **스코어링 TOP5 분석**을 시작합니다 (기준일: {trade_date})")
    async with _analysis_lock:
        ch = interaction.channel
        if isinstance(ch, discord.abc.Messageable):
            await _run_top5_analysis(ch, trade_date)
            _log("INFO", "SLASH_TOP5_DONE", f"date={trade_date}")
        else:
            _log("WARN", "SLASH_TOP5_INVALID_CHANNEL", "interaction channel is not Messageable")
            await interaction.followup.send("❌ 이 채널에서는 분석을 실행할 수 없습니다.")


# ─── Slash Command: /잔고 ──────────────────────────────────────
@tree.command(name="잔고", description="한국투자증권 계좌 잔고를 조회합니다")
async def balance_cmd(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    _log("INFO", "SLASH_BALANCE_START", _interaction_actor(interaction))

    if not kis.is_configured:
        _log("WARN", "SLASH_BALANCE_BLOCKED", "KIS API not configured")
        await interaction.followup.send("⚠️ KIS API가 설정되지 않았습니다. `.env`에 KIS 인증 정보를 추가하세요.")
        return

    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, kis.get_balance, "ALL")
        holdings = data["holdings"]
        summary = data["summary"]

        if not holdings:
            desc = "보유 종목이 없습니다."
        else:
            lines = []
            for h in holdings:
                pnl_emoji = "🟢" if h["pnl"] >= 0 else "🔴"
                currency = h.get("currency", _currency_of_market(h.get("market", "KR")))
                lines.append(
                    f"**[{h.get('market', 'KR')}] {h['name']}** (`{h['ticker']}`) — {h['qty']}주\n"
                    f"  평균가 {_format_money(h['avg_price'], currency)} → "
                    f"현재 {_format_money(h['current_price'], currency)} "
                    f"{pnl_emoji} {_format_money(h['pnl'], currency)} ({h['pnl_rate']:+.2f}%)"
                )
            desc = "\n".join(lines)

        mode_label = "🧪 모의투자" if kis.virtual else "💰 실전투자"
        embed = discord.Embed(
            title=f"💰 계좌 잔고 ({mode_label})",
            description=desc,
            color=0x0066FF,
            timestamp=datetime.datetime.now(),
        )
        if summary:
            krw = summary.get("KRW", {})
            usd = summary.get("USD", {})
            embed.add_field(
                name="KRW 요약",
                value=(
                    f"평가액: {_format_money(krw.get('total_eval', 0), 'KRW')}\n"
                    f"손익: {_format_money(krw.get('total_pnl', 0), 'KRW')}\n"
                    f"예수금: {_format_money(krw.get('cash', 0), 'KRW')}"
                ),
                inline=True,
            )
            embed.add_field(
                name="USD 요약",
                value=(
                    f"평가액: {_format_money(usd.get('total_eval', 0), 'USD')}\n"
                    f"손익: {_format_money(usd.get('total_pnl', 0), 'USD')}\n"
                    f"예수금: {_format_money(usd.get('cash', 0), 'USD')}"
                ),
                inline=True,
            )
            embed.add_field(name="보유 종목 수", value=f"{len(holdings)}개", inline=True)

        await interaction.followup.send(embed=embed)
        _log(
            "INFO",
            "SLASH_BALANCE_DONE",
            f"holdings={len(holdings)} krw_eval={summary.get('KRW', {}).get('total_eval', 0)} "
            f"usd_eval={summary.get('USD', {}).get('total_eval', 0)}",
        )
    except Exception as e:
        _log("ERROR", "SLASH_BALANCE_ERROR", str(e)[:200])
        await interaction.followup.send(f"❌ 잔고 조회 실패: {str(e)[:500]}")


# ─── Slash Command: /매수 ──────────────────────────────────────
@tree.command(name="매수", description="종목을 매수합니다 (수량 생략 시 예산 상한 기준 자동 계산)")
@app_commands.describe(
    ticker="매수할 종목 코드 (예: 005930, AAPL)",
    qty="매수 수량 (생략 시 시장별 수동 예산 상한 기준)",
)
async def buy_cmd(
    interaction: discord.Interaction,
    ticker: str,
    qty: int | None = None,
):
    await interaction.response.defer(thinking=True)
    _log("INFO", "SLASH_BUY_START", f"{_interaction_actor(interaction)} ticker={ticker} qty={qty}")

    if not _is_allowed_channel(interaction.channel_id):
        _log("WARN", "SLASH_BUY_BLOCKED", f"허용되지 않은 채널 channel={interaction.channel_id}")
        await interaction.followup.send("❌ 이 채널에서는 사용할 수 없습니다.")
        return

    if not kis.is_configured:
        _log("WARN", "SLASH_BUY_BLOCKED", "KIS API not configured")
        await interaction.followup.send("⚠️ KIS API가 설정되지 않았습니다.")
        return

    ticker = ticker.strip().upper()
    format_error = _validate_ticker_format(ticker)
    if format_error:
        _log("WARN", "SLASH_BUY_INVALID_TICKER", f"ticker={ticker} reason={format_error}")
        await interaction.followup.send(f"❌ {format_error}")
        return

    market = _market_of_ticker(ticker)
    if market == "US" and not kis.enable_us_trading:
        _log("WARN", "SLASH_BUY_US_DISABLED", f"ticker={ticker}")
        await interaction.followup.send(
            "ℹ️ 미국 주문은 비활성화되어 있습니다. `.env`의 "
            "`ENABLE_US_TRADING=true` 설정 후 사용하세요."
        )
        return

    if qty is not None and qty <= 0:
        _log("WARN", "SLASH_BUY_INVALID_QTY", f"ticker={ticker} qty={qty}")
        await interaction.followup.send("❌ 수량은 1 이상이어야 합니다.")
        return

    if not _is_market_open_now(market):
        _log("INFO", "SLASH_BUY_MARKET_CLOSED", f"market={market} ticker={ticker}")
        await interaction.followup.send(
            f"ℹ️ `{ticker}`({market}) 현재 장외/휴장 상태라 주문 버튼을 표시하지 않습니다."
        )
        return

    normalized = kis.normalize_ticker(ticker, market)
    currency = _currency_of_market(market)
    budget_cap = kis.us_max_order_amount if market == "US" else kis.max_order_amount
    loop = asyncio.get_running_loop()

    try:
        price = await loop.run_in_executor(None, kis.get_price, normalized, market)
    except Exception as e:
        _log("ERROR", "SLASH_BUY_PRICE_ERROR", f"ticker={normalized} error={str(e)[:200]}")
        await interaction.followup.send(f"❌ 현재가 조회 실패: {str(e)[:300]}")
        return

    if price <= 0:
        _log("WARN", "SLASH_BUY_INVALID_PRICE", f"market={market} ticker={normalized} price={price}")
        await interaction.followup.send(
            f"❌ `{normalized}`({market}) 현재가를 확인할 수 없습니다. 티커를 다시 확인해주세요."
        )
        return

    auto_qty = False
    buy_qty = qty
    if buy_qty is None:
        auto_qty = True
        buy_qty = int(budget_cap // price)
        if buy_qty <= 0:
            _log("WARN", "SLASH_BUY_BUDGET_TOO_LOW", f"market={market} ticker={normalized} price={price}")
            await interaction.followup.send(
                f"⚠️ 예산 상한({_format_money(budget_cap, currency)}) 대비 "
                f"현재가({_format_money(price, currency)})가 높아 1주도 매수할 수 없습니다."
            )
            return

    expected_amount = buy_qty * price
    if expected_amount > budget_cap:
        _log(
            "WARN",
            "SLASH_BUY_OVER_CAP",
            f"market={market} ticker={normalized} qty={buy_qty} amount={expected_amount} cap={budget_cap}",
        )
        await interaction.followup.send(
            f"❌ 주문 예상금액({_format_money(expected_amount, currency)})이 "
            f"수동 예산 상한({_format_money(budget_cap, currency)})을 초과합니다.\n"
            "수량을 줄이거나 예산 상한 환경변수를 조정하세요."
        )
        return

    view = BuyConfirmView(
        ticker=normalized,
        name=normalized,
        qty=buy_qty,
        price=price,
        market=market,
        currency=currency,
        reason="수동 /매수 주문",
    )
    mode_label = "🧪 모의투자" if kis.virtual else "💰 실전투자"
    qty_rule_text = (
        f"자동 계산(상한 {_format_money(budget_cap, currency)} 기준)"
        if auto_qty
        else f"사용자 입력 ({buy_qty}주)"
    )
    embed = discord.Embed(
        title="🛒 매수 확인",
        description=(
            f"**시장:** {market}\n"
            f"**종목:** `{normalized}`\n"
            f"**현재가:** {_format_money(price, currency)}\n"
            f"**매수 수량:** {buy_qty}주\n"
            f"**수량 기준:** {qty_rule_text}\n"
            f"**예상 금액:** {_format_money(expected_amount, currency)}\n"
            f"**수동 예산 상한:** {_format_money(budget_cap, currency)}\n\n"
            f"매수하시겠습니까?"
        ),
        color=0x00FF00,
    )
    embed.set_footer(text=f"{mode_label} | {currency}")
    await interaction.followup.send(embed=embed, view=view)
    _log(
        "INFO",
        "SLASH_BUY_PROMPT",
        f"market={market} ticker={normalized} qty={buy_qty} price={price}",
    )


# ─── Slash Command: /매도 ──────────────────────────────────────
@tree.command(name="매도", description="보유 종목을 매도합니다 (수량 생략 시 전량 매도)")
@app_commands.describe(
    ticker="매도할 종목 코드 (예: 005930)",
    qty="매도 수량 (생략 시 전량 매도)",
)
async def sell_cmd(
    interaction: discord.Interaction,
    ticker: str,
    qty: int | None = None,
):
    await interaction.response.defer(thinking=True)
    _log("INFO", "SLASH_SELL_START", f"{_interaction_actor(interaction)} ticker={ticker} qty={qty}")

    if not _is_allowed_channel(interaction.channel_id):
        _log("WARN", "SLASH_SELL_BLOCKED", f"허용되지 않은 채널 channel={interaction.channel_id}")
        await interaction.followup.send("❌ 이 채널에서는 사용할 수 없습니다.")
        return

    if not kis.is_configured:
        _log("WARN", "SLASH_SELL_BLOCKED", "KIS API not configured")
        await interaction.followup.send("⚠️ KIS API가 설정되지 않았습니다.")
        return

    ticker = ticker.strip().upper()
    market = _market_of_ticker(ticker)
    normalized = kis.normalize_ticker(ticker, market)
    holding: dict | None = None
    loop = asyncio.get_running_loop()

    if qty is not None and qty <= 0:
        _log("WARN", "SLASH_SELL_INVALID_QTY", f"ticker={ticker} qty={qty}")
        await interaction.followup.send("❌ 수량은 1 이상이어야 합니다.")
        return

    # 잔고에서 보유 정보 조회
    try:
        balance_data = await loop.run_in_executor(None, kis.get_balance, "ALL")
        holding = next(
            (
                h
                for h in balance_data["holdings"]
                if h["ticker"] == normalized and h.get("market", market) == market
            ),
            None,
        )
    except Exception as e:
        _log("ERROR", "SLASH_SELL_BALANCE_ERROR", str(e)[:200])
        await interaction.followup.send(f"❌ 잔고 조회 실패: {str(e)[:300]}")
        return

    if not holding:
        _log("WARN", "SLASH_SELL_NO_HOLDING", f"market={market} ticker={normalized}")
        await interaction.followup.send(f"⚠️ `{normalized}`({market}) 보유 내역이 없습니다.")
        return

    sell_qty = qty if qty is not None else holding["qty"]
    stock_name = holding["name"]
    avg_price = holding["avg_price"]
    currency = holding.get("currency", _currency_of_market(market))

    view = SellConfirmView(
        ticker=holding["ticker"],
        name=stock_name,
        qty=sell_qty,
        avg_price=avg_price,
        market=market,
        currency=currency,
        exchange=holding.get("exchange", ""),
    )
    mode_label = "🧪 모의투자" if kis.virtual else "💰 실전투자"
    embed = discord.Embed(
        title="🔴 매도 확인",
        description=(
            f"**시장:** {market}\n"
            f"**종목:** {stock_name} (`{holding['ticker']}`)\n"
            f"**수량:** {sell_qty}주\n\n매도하시겠습니까?"
        ),
        color=0xFF0000,
    )
    embed.set_footer(text=f"{mode_label} | {currency}")
    await interaction.followup.send(embed=embed, view=view)
    _log(
        "INFO",
        "SLASH_SELL_PROMPT",
        f"market={market} ticker={holding['ticker']} qty={sell_qty} avg_price={avg_price}",
    )


# ─── Slash Command: /상태 ──────────────────────────────────────
@tree.command(name="상태", description="오늘의 자동매매 실행 상태를 확인합니다")
async def status_cmd(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    _log("INFO", "SLASH_STATUS_START", _interaction_actor(interaction))

    if not _is_allowed_channel(interaction.channel_id):
        _log("WARN", "SLASH_STATUS_BLOCKED", f"허용되지 않은 채널 channel={interaction.channel_id}")
        await interaction.followup.send("❌ 이 채널에서는 사용할 수 없습니다.")
        return

    states = get_daily_state()
    if not states:
        _log("INFO", "SLASH_STATUS_EMPTY", "today has no auto-trading state")
        await interaction.followup.send("📋 오늘 실행된 자동매매가 없습니다.")
        return

    lines = []
    for s in states:
        emoji = {
            "morning_buy": "🌅",
            "afternoon_sell": "🌇",
            "us_morning_buy": "🇺🇸🌅",
            "us_afternoon_sell": "🇺🇸🌇",
        }.get(
            s["action"], "🔔"
        )
        lines.append(
            f"{emoji} **{s['action']}** — {s['completed_at'][:16]}\n"
            f"   {s['details']}"
        )

    embed = discord.Embed(
        title=f"📋 오늘의 자동매매 상태 ({datetime.date.today()})",
        description="\n\n".join(lines),
        color=0x0066FF,
        timestamp=datetime.datetime.now(),
    )
    await interaction.followup.send(embed=embed)
    _log("INFO", "SLASH_STATUS_DONE", f"state_count={len(states)}")


# ─── Slash Command: /봇정보 ────────────────────────────────────
@tree.command(name="봇정보", description="봇 스케줄 · 설정 · 계좌 · 실행 이력을 확인합니다")
async def bot_info_cmd(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    _log("INFO", "SLASH_BOTINFO_START", _interaction_actor(interaction))

    if not _is_allowed_channel(interaction.channel_id):
        _log("WARN", "SLASH_BOTINFO_BLOCKED", f"허용되지 않은 채널 channel={interaction.channel_id}")
        await interaction.followup.send("❌ 이 채널에서는 사용할 수 없습니다.")
        return

    now = datetime.datetime.now(KST)
    now_ny = datetime.datetime.now(NY_TZ)
    mode_label = "🧪 모의투자" if kis.virtual else "💰 실전투자"

    # 버전 정보
    version_line = f"**버전:** v{BOT_VERSION}"

    # 다음 실행 시각 계산
    today = now.date()
    buy_time = datetime.datetime.combine(
        today, datetime.time(_buy_h, _buy_m), tzinfo=KST
    )
    sell_time = datetime.datetime.combine(
        today, datetime.time(_sell_h, _sell_m), tzinfo=KST
    )
    if buy_time <= now:
        buy_time += datetime.timedelta(days=1)
    if sell_time <= now:
        sell_time += datetime.timedelta(days=1)

    buy_remaining = buy_time - now
    sell_remaining = sell_time - now
    buy_h_r, buy_m_r = divmod(int(buy_remaining.total_seconds()) // 60, 60)
    sell_h_r, sell_m_r = divmod(int(sell_remaining.total_seconds()) // 60, 60)

    us_buy_h_r, us_buy_m_r = 0, 0
    us_sell_h_r, us_sell_m_r = 0, 0
    if ENABLE_US_TRADING:
        us_today = now_ny.date()
        us_buy_time = datetime.datetime.combine(
            us_today, datetime.time(_us_buy_h, _us_buy_m), tzinfo=NY_TZ
        )
        us_sell_time = datetime.datetime.combine(
            us_today, datetime.time(_us_sell_h, _us_sell_m), tzinfo=NY_TZ
        )
        if us_buy_time <= now_ny:
            us_buy_time += datetime.timedelta(days=1)
        if us_sell_time <= now_ny:
            us_sell_time += datetime.timedelta(days=1)
        us_buy_remaining = us_buy_time - now_ny
        us_sell_remaining = us_sell_time - now_ny
        us_buy_h_r, us_buy_m_r = divmod(int(us_buy_remaining.total_seconds()) // 60, 60)
        us_sell_h_r, us_sell_m_r = divmod(int(us_sell_remaining.total_seconds()) // 60, 60)

    # 오늘 상태
    states = get_daily_state()
    morning_done = any(s["action"] == "morning_buy" for s in states)
    afternoon_done = any(s["action"] == "afternoon_sell" for s in states)
    us_morning_done = any(s["action"] == "us_morning_buy" for s in states)
    us_afternoon_done = any(s["action"] == "us_afternoon_sell" for s in states)
    kr_market_open = _is_market_day("KR")
    us_market_open = _is_market_day("US")

    status_lines = [
        f"**📅 KR 오늘:** {today} ({'거래일 ✅' if kr_market_open else '휴장일 ❌'})",
        f"**📅 US 오늘:** {now_ny.date()} ({'거래일 ✅' if us_market_open else '휴장일 ❌'})",
        f"**⏰ 현재 시각:** {now.strftime('%H:%M:%S')} KST",
        f"**⏰ NY 시각:** {now_ny.strftime('%H:%M:%S')} ET",
        "",
        "── **KR 자동매매 스케줄** ──",
        f"🌅 **아침 매수:** {AUTO_BUY_TIME} KST → "
        f"{'✅ 완료' if morning_done else f'⏳ {buy_h_r}시간 {buy_m_r}분 후'}",
        f"🌇 **오후 매도:** {AUTO_SELL_TIME} KST → "
        f"{'✅ 완료' if afternoon_done else f'⏳ {sell_h_r}시간 {sell_m_r}분 후'}",
    ]
    if ENABLE_US_TRADING:
        status_lines.extend(
            [
                "",
                "── **US 자동매매 스케줄** ──",
                f"🌅 **아침 매수:** {US_AUTO_BUY_TIME} ET → "
                f"{'✅ 완료' if us_morning_done else f'⏳ {us_buy_h_r}시간 {us_buy_m_r}분 후'}",
                f"🌇 **오후 매도:** {US_AUTO_SELL_TIME} ET → "
                f"{'✅ 완료' if us_afternoon_done else f'⏳ {us_sell_h_r}시간 {us_sell_m_r}분 후'}",
            ]
        )
    status_lines.extend(
        [
            "",
            f"🔔 **손절/익절:** {MONITOR_INTERVAL_MIN}분 간격 감시 중",
            "",
            "── **설정** ──",
            f"📊 **KR 매수 종목 수:** {DAY_TRADE_PICKS}개",
            f"📊 **US 매수 종목 수:** {US_DAY_TRADE_PICKS}개",
            f"💸 **KR 자동예산 비율:** {AUTO_BUY_BUDGET_RATIO * 100:.1f}%",
            f"💸 **US 자동예산 비율:** {US_AUTO_BUY_BUDGET_RATIO * 100:.1f}%",
            f"🏦 **KR 기준 자금(anchor):** {_format_money(get_budget_anchor('KR'), 'KRW')}",
            f"🏦 **US 기준 자금(anchor):** {_format_money(get_budget_anchor('US'), 'USD')}",
            f"🧪 **KR 수동 예산:** {_format_money(kis.max_order_amount, 'KRW')}",
            f"🧪 **US 수동 예산:** {_format_money(kis.us_max_order_amount, 'USD')}",
            f"🔴 **손절 라인:** {STOP_LOSS_PCT}%",
            f"🟢 **익절 라인:** {TAKE_PROFIT_PCT}%",
            f"🏦 **매매 모드:** {mode_label}",
            f"🤖 **분석 모델:** {config.get('deep_think_llm', 'N/A')}",
            version_line,
        ]
    )

    if kis.is_configured:
        try:
            loop = asyncio.get_running_loop()
            bal = await loop.run_in_executor(None, kis.get_balance, "ALL")
            sm = bal.get("summary", {})
            holdings_count = len(bal.get("holdings", []))
            status_lines.append("")
            status_lines.append("── **계좌** ──")
            status_lines.append(f"💵 **KR 예수금:** {_format_money(sm.get('KRW', {}).get('cash', 0), 'KRW')}")
            status_lines.append(f"💵 **US 예수금:** {_format_money(sm.get('USD', {}).get('cash', 0), 'USD')}")
            status_lines.append(f"📦 **보유종목:** {holdings_count}개")
            status_lines.append(
                f"📈 **KR 평가액:** {_format_money(sm.get('KRW', {}).get('total_eval', 0), 'KRW')}"
            )
            status_lines.append(
                f"📈 **US 평가액:** {_format_money(sm.get('USD', {}).get('total_eval', 0), 'USD')}"
            )
        except Exception:
            pass

    if states:
        status_lines.append("")
        status_lines.append("── **오늘 실행 이력** ──")
        for s in states:
            emoji = {
                "morning_buy": "🌅",
                "afternoon_sell": "🌇",
                "us_morning_buy": "🇺🇸🌅",
                "us_afternoon_sell": "🇺🇸🌇",
            }.get(
                s["action"], "🔔"
            )
            status_lines.append(
                f"{emoji} {s['action']} — {s['completed_at'][:16]} | {s['details']}"
            )

    embed = discord.Embed(
        title="🤖 TradingAgents 봇 정보",
        description="\n".join(status_lines),
        color=0x0066FF,
        timestamp=now,
    )
    embed.set_footer(text="TradingAgents 데이 트레이딩 시스템")
    await interaction.followup.send(embed=embed)
    _log(
        "INFO",
        "SLASH_BOTINFO_DONE",
        f"kr_open={kr_market_open} us_open={us_market_open} state_count={len(states)}",
    )


# ─── Slash Command: /스코어링 ──────────────────────────────────
@tree.command(name="스코어링", description="실시간 스코어링 후보를 조회합니다")
@app_commands.describe(
    market="조회할 시장 (기본: KR)",
    count="표시할 개수 (1~15, 기본 10)",
    exclude_held="보유 종목 제외 여부 (기본: 제외)",
)
@app_commands.choices(
    market=[
        app_commands.Choice(name="한국 (KR)", value="KR"),
        app_commands.Choice(name="미국 (US)", value="US"),
    ]
)
async def scoring_cmd(
    interaction: discord.Interaction,
    market: app_commands.Choice[str] | None = None,
    count: int = 10,
    exclude_held: bool = True,
):
    await interaction.response.defer(thinking=True)
    _log("INFO", "SLASH_SCORING_START", _interaction_actor(interaction))

    if not _is_allowed_channel(interaction.channel_id):
        _log("WARN", "SLASH_SCORING_BLOCKED", f"허용되지 않은 채널 channel={interaction.channel_id}")
        await interaction.followup.send("❌ 이 채널에서는 사용할 수 없습니다.")
        return

    if count < 1 or count > 15:
        await interaction.followup.send("❌ count는 1~15 범위로 입력해주세요.")
        return

    selected = market.value if market else "KR"
    title_market = {"KR": "한국", "US": "미국"}.get(selected, "한국")
    mode_label = "🧪 모의투자" if kis.virtual else "💰 실전투자"
    loop = asyncio.get_running_loop()

    if selected == "KR" and not kis.is_configured:
        await interaction.followup.send(
            "⚠️ KR 스코어링은 KIS API 설정이 필요합니다. `.env`를 확인해주세요."
        )
        return

    status = await interaction.followup.send(
        f"📊 {title_market} 실시간 스코어링 실행 중…",
        wait=True,
    )

    # 보유 종목 제외를 켜도 count를 채우기 위해 여유분을 더 조회한다.
    request_count = max(10, count * 2) if exclude_held else max(10, count)
    try:
        if selected == "KR":
            candidates = await _compute_stock_scores(count=request_count)
        else:
            candidates = await _compute_us_stock_scores(count=request_count)
    except Exception as e:
        _log("ERROR", "SLASH_SCORING_ERROR", f"market={selected} error={str(e)[:200]}")
        await status.edit(content=f"❌ 스코어링 실행 실패: {str(e)[:300]}")
        return

    if not candidates:
        await status.edit(content=f"❌ {title_market} 스코어링 후보가 없습니다.")
        return

    filtered = candidates
    held_tickers: set[str] = set()
    if exclude_held and kis.is_configured:
        try:
            balance_data = await loop.run_in_executor(None, kis.get_balance, selected)
            held_tickers = {h["ticker"] for h in balance_data.get("holdings", [])}
            filtered = [c for c in candidates if c["ticker"] not in held_tickers]
        except Exception as e:
            _log("WARN", "SLASH_SCORING_HELD_FETCH_FAIL", f"market={selected} error={str(e)[:160]}")
            filtered = candidates

    if not filtered:
        await status.edit(content="📋 후보 종목이 모두 이미 보유 중입니다.")
        return

    top_list = filtered[:count]
    currency = "USD" if selected == "US" else "KRW"
    lines = []
    for idx, c in enumerate(top_list, 1):
        sig_str = ", ".join(c.get("signals", []))
        lines.append(
            f"**{idx}. {c['name']} (`{c['ticker']}`)** — **{c['score']}점**\n"
            f"{_format_money(c.get('price', 0), currency)} ({float(c.get('prdy_ctrt', 0)):+.2f}%) | {sig_str}"
        )

    embed = discord.Embed(
        title=f"🏆 {title_market} 실시간 스코어링 TOP {len(top_list)}",
        description="\n".join(lines),
        color=0x0066FF,
        timestamp=datetime.datetime.now(NY_TZ if selected == "US" else KST),
    )
    held_note = f"ON ({len(held_tickers)}개 제외)" if exclude_held else "OFF"
    embed.set_footer(text=f"{mode_label} | 보유 제외: {held_note}")
    await status.edit(content=None, embed=embed)
    _log(
        "INFO",
        "SLASH_SCORING_DONE",
        f"market={selected} requested={request_count} shown={len(top_list)} exclude_held={exclude_held}",
    )


# ─── Slash Command: /스코어규칙 ─────────────────────────────────
@tree.command(name="스코어규칙", description="자동매매 스코어링 규칙을 조회합니다")
@app_commands.describe(market="조회할 시장 (기본: 전체)")
@app_commands.choices(
    market=[
        app_commands.Choice(name="전체", value="ALL"),
        app_commands.Choice(name="한국 (KR)", value="KR"),
        app_commands.Choice(name="미국 (US)", value="US"),
    ]
)
async def scoring_rules_cmd(
    interaction: discord.Interaction,
    market: app_commands.Choice[str] | None = None,
):
    await interaction.response.defer(thinking=True)
    _log("INFO", "SLASH_SCORING_RULES_START", _interaction_actor(interaction))

    if not _is_allowed_channel(interaction.channel_id):
        _log("WARN", "SLASH_SCORING_RULES_BLOCKED", f"허용되지 않은 채널 channel={interaction.channel_id}")
        await interaction.followup.send("❌ 이 채널에서는 사용할 수 없습니다.")
        return

    selected = market.value if market else "ALL"
    title_market = {"ALL": "전체", "KR": "한국", "US": "미국"}.get(selected, "전체")
    mode_label = "🧪 모의투자" if kis.virtual else "💰 실전투자"

    embed = discord.Embed(
        title=f"📐 스코어링 규칙 ({title_market})",
        description=(
            "자동매매는 **룰 기반 스코어링 → 상위 후보만 AI 분석** 순서로 동작합니다.\n"
            "아래 점수는 현재 코드 기준 고정 규칙입니다."
        ),
        color=0x0066FF,
        timestamp=datetime.datetime.now(),
    )

    if selected in ("ALL", "KR"):
        kr_wl = ", ".join(kis.kr_watchlist[:8])
        if len(kis.kr_watchlist) > 8:
            kr_wl += f" 외 {len(kis.kr_watchlist) - 8}개"
        embed.add_field(
            name="🇰🇷 KR 점수식 (대형주+ETF 워치리스트)",
            value=(
                f"후보 풀: `KR_WATCHLIST` ({len(kis.kr_watchlist)}종목)\n"
                f"`{kr_wl}`\n"
                "• 워치리스트 기본: `+30` (대형주/ETF 신뢰)\n"
                "• 등락률 `0~2%`: `+25` (안정상승), `2~5%`: `+15`\n"
                "• 시총 랭크 진입: `+10` (응답 가능 시)\n"
                "• 거래량 랭크 진입: `+5` (응답 가능 시)\n"
                "필터: 등락률 `>8%` 또는 `<-5%` 제외\n"
                f"AI 분석: 상위 `{DAY_TRADE_PICKS}`개\n"
                "오후 매도: 워치리스트 종목은 **스윙 보유** (손절/익절만)"
            ),
            inline=False,
        )

    if selected in ("ALL", "US"):
        us_status = "활성" if ENABLE_US_TRADING else "비활성"
        us_wl = ", ".join(kis.us_watchlist[:8])
        if len(kis.us_watchlist) > 8:
            us_wl += f" 외 {len(kis.us_watchlist) - 8}개"
        embed.add_field(
            name="🇺🇸 US 점수식 (대형주+ETF 워치리스트)",
            value=(
                f"후보 풀: `US_WATCHLIST` ({len(kis.us_watchlist)}종목)\n"
                f"`{us_wl}`\n"
                "• 워치리스트 기본: `+30` (대형주/ETF 신뢰)\n"
                "• 등락률 `0~2%`: `+25` (안정상승), `2~5%`: `+15`\n"
                "• 시총 랭크 진입: `+10` (응답 가능 시)\n"
                "• 거래량 랭크 진입: `+5` (응답 가능 시)\n"
                "필터: 등락률 `>8%` 또는 `<-5%` 제외\n"
                f"AI 분석: 상위 `{US_DAY_TRADE_PICKS}`개\n"
                "오후 매도: 워치리스트 종목은 **스윙 보유** (손절/익절만)\n"
                f"현재 US 자동매매: **{us_status}** (`ENABLE_US_TRADING={str(ENABLE_US_TRADING).lower()}`)"
            ),
            inline=False,
        )

    embed.set_footer(text=f"{mode_label} | /스코어규칙")
    await interaction.followup.send(embed=embed)
    _log("INFO", "SLASH_SCORING_RULES_DONE", f"market={selected}")


# ─── Slash Command: /수익 ──────────────────────────────────────
@tree.command(name="수익", description="누적 매매 수익 현황을 조회합니다")
async def pnl_cmd(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    _log("INFO", "SLASH_PNL_START", _interaction_actor(interaction))

    if not _is_allowed_channel(interaction.channel_id):
        _log("WARN", "SLASH_PNL_BLOCKED", f"허용되지 않은 채널 channel={interaction.channel_id}")
        await interaction.followup.send("❌ 이 채널에서는 사용할 수 없습니다.")
        return

    by_ccy = get_total_pnl_by_currency()
    krw = by_ccy.get("KRW", get_total_pnl(currency="KRW"))
    usd = by_ccy.get("USD", get_total_pnl(currency="USD"))
    ticker_krw = get_ticker_summary(currency="KRW")
    ticker_usd = get_ticker_summary(currency="USD")
    recent_krw = get_recent_pnl(5, currency="KRW")
    recent_usd = get_recent_pnl(5, currency="USD")

    desc_lines = [
        f"KRW 손익: {_format_money(krw['total_pnl'], 'KRW')} | "
        f"거래 {krw['trade_count']}회 | 승률 {krw['win_rate']}%",
        f"USD 손익: {_format_money(usd['total_pnl'], 'USD')} | "
        f"거래 {usd['trade_count']}회 | 승률 {usd['win_rate']}%",
    ]

    tone_total = krw["total_pnl"] + usd["total_pnl"]
    embed = discord.Embed(
        title="📊 매매 수익 현황 (통화 분리)",
        description="\n".join(desc_lines),
        color=0x00FF00 if tone_total >= 0 else 0xFF0000,
        timestamp=datetime.datetime.now(),
    )

    if ticker_krw:
        lines = []
        for t in ticker_krw[:5]:
            emoji = "🟢" if t["total_pnl"] >= 0 else "🔴"
            lines.append(
                f"{emoji} [{t['market']}] {t['name']} (`{t['ticker']}`) "
                f"— {t['count']}회 | {_format_money(t['total_pnl'], 'KRW')} | 평균 {t['avg_pnl_rate']:+.1f}%"
            )
        embed.add_field(name="🏢 KRW 종목별", value="\n".join(lines), inline=False)

    if ticker_usd:
        lines = []
        for t in ticker_usd[:5]:
            emoji = "🟢" if t["total_pnl"] >= 0 else "🔴"
            lines.append(
                f"{emoji} [{t['market']}] {t['name']} (`{t['ticker']}`) "
                f"— {t['count']}회 | {_format_money(t['total_pnl'], 'USD')} | 평균 {t['avg_pnl_rate']:+.1f}%"
            )
        embed.add_field(name="🌎 USD 종목별", value="\n".join(lines), inline=False)

    if recent_krw:
        lines = []
        for r in recent_krw[:3]:
            emoji = "🟢" if r["pnl"] >= 0 else "🔴"
            lines.append(
                f"{emoji} {r['name']} — {_format_money(r['pnl'], 'KRW')} "
                f"({r['pnl_rate']:+.1f}%) | {r['created_at']}"
            )
        embed.add_field(name="🕗 최근 KRW 손익", value="\n".join(lines), inline=False)

    if recent_usd:
        lines = []
        for r in recent_usd[:3]:
            emoji = "🟢" if r["pnl"] >= 0 else "🔴"
            lines.append(
                f"{emoji} {r['name']} — {_format_money(r['pnl'], 'USD')} "
                f"({r['pnl_rate']:+.1f}%) | {r['created_at']}"
            )
        embed.add_field(name="🕗 최근 USD 손익", value="\n".join(lines), inline=False)

    embed.set_footer(text="TradingAgents 매매 이력 (통화 분리, 마지막 초기화 이후 기준)")
    await interaction.followup.send(embed=embed)
    _log(
        "INFO",
        "SLASH_PNL_DONE",
        f"krw_total={krw['total_pnl']} usd_total={usd['total_pnl']}",
    )


@tree.command(name="수익초기화", description="누적 실현손익 집계 기준을 초기화합니다")
@app_commands.describe(currency="초기화할 통화 범위 (기본: 전체)")
@app_commands.choices(
    currency=[
        app_commands.Choice(name="전체", value="ALL"),
        app_commands.Choice(name="KRW", value="KRW"),
        app_commands.Choice(name="USD", value="USD"),
    ]
)
async def pnl_reset_cmd(
    interaction: discord.Interaction,
    currency: app_commands.Choice[str] | None = None,
):
    await interaction.response.defer(thinking=True, ephemeral=True)

    selected = currency.value if currency else "ALL"
    _log("INFO", "SLASH_PNL_RESET_START", f"{_interaction_actor(interaction)} currency={selected}")

    if not _is_allowed_channel(interaction.channel_id):
        _log("WARN", "SLASH_PNL_RESET_BLOCKED", f"허용되지 않은 채널 channel={interaction.channel_id}")
        await interaction.followup.send("❌ 이 채널에서는 사용할 수 없습니다.", ephemeral=True)
        return

    target_currency = None if selected == "ALL" else selected
    summary_targets = ("KRW", "USD") if target_currency is None else (target_currency,)
    summary = {
        code: get_total_pnl(currency=code)
        for code in summary_targets
    }
    reset_at = reset_pnl_history(
        currency=target_currency,
        reset_by=str(interaction.user),
        reason=f"discord:/수익초기화 by {getattr(interaction.user, 'id', 'unknown')}",
    )

    cleared_lines = [
        f"- {code}: {_format_money(data['total_pnl'], code)} | 거래 {data['trade_count']}회 | 승률 {data['win_rate']}%"
        for code, data in summary.items()
    ]
    target_label = "전체 통화" if target_currency is None else target_currency
    message = "\n".join(
        [
            f"✅ `{target_label}` 수익 집계 기준을 초기화했습니다.",
            f"기준 시각: `{reset_at}`",
            *cleared_lines,
            "과거 손익 로그는 보존되며, 이제 `/수익`은 이 시각 이후 실현손익만 집계합니다.",
        ]
    )
    await interaction.followup.send(message, ephemeral=True)
    _log("INFO", "SLASH_PNL_RESET_DONE", f"currency={selected} reset_at={reset_at}")


# ─── 스케줄: 아침 자동매수 (09:30 KST) ───────────────────


@tasks.loop(time=datetime.time(hour=_buy_h, minute=_buy_m, tzinfo=KST))
async def morning_auto_buy():
    """매일 아침(기본 09:30) 실시간 스코어링 → 상위 AI 분석 → 자동 매수.

    1) 실시간 KIS 순위 API 4종으로 멀티시그널 스코어링
    2) 상위 DAY_TRADE_PICKS개 후보만 순차 AI 분석 (BUY 판정만 수집)
    3) 통장 전액 ÷ BUY 종목수 균등분배 → 시장가 매수
    """
    if not ALLOWED_CHANNEL_IDS or not kis.is_configured:
        _log("INFO", "AUTO_BUY_SKIP", "채널 미설정 또는 KIS 미설정")
        return
    if not _is_market_day("KR"):
        _log("INFO", "AUTO_BUY_SKIP", "오늘은 휴장일")
        return
    if _analysis_lock.locked():
        _log("INFO", "AUTO_BUY_SKIP", "analysis lock 사용 중")
        return
    # 재시작 중복 방지: 오늘 이미 매수 완료했으면 스킵
    if is_action_done("morning_buy"):
        _log("INFO", "AUTO_BUY_SKIP", "오늘 morning_buy 이미 완료")
        return

    channel_id = next(iter(ALLOWED_CHANNEL_IDS))
    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        _log("WARN", "AUTO_BUY_SKIP", f"채널 접근 실패 channel_id={channel_id}")
        return

    trade_date = str(datetime.date.today())
    mode_label = "🧪 모의투자" if kis.virtual else "💰 실전투자"
    loop = asyncio.get_running_loop()

    async with _analysis_lock:
        _log("INFO", "AUTO_BUY_START", f"date={trade_date} target_picks={DAY_TRADE_PICKS}")
        await channel.send(
            f"🌅 **대형주+ETF 자동매수** 시작 ({AUTO_BUY_TIME} KST)"
        )

        # ── 1) 워치리스트(대형주+ETF) 스코어링 ──
        try:
            scoring_msg = await channel.send("📊 워치리스트(대형주+ETF) 스코어링 중…")
            candidates = await _compute_stock_scores(count=10)
        except Exception as e:
            _log("ERROR", "AUTO_BUY_SCORING_ERROR", str(e)[:200])
            await channel.send(f"❌ 순위 조회 실패: {str(e)[:300]}")
            return

        if not candidates:
            _log("INFO", "AUTO_BUY_NO_CANDIDATE", "스코어링 결과 후보 없음")
            await scoring_msg.edit(content="❌ 매수 후보가 없습니다. (시장 상황 부적합)")
            return

        # 이미 보유 중인 종목 제외
        try:
            balance_data = await loop.run_in_executor(None, kis.get_balance, "KR")
            held_tickers = {h["ticker"] for h in balance_data.get("holdings", [])}
        except Exception:
            held_tickers = set()

        filtered = [c for c in candidates if c["ticker"] not in held_tickers]
        if not filtered:
            _log("INFO", "AUTO_BUY_ALL_HELD", "후보가 모두 보유 종목")
            await scoring_msg.edit(content="📋 스코어링 후보가 모두 이미 보유 중입니다.")
            return

        _log("INFO", "AUTO_BUY_CANDIDATES", f"raw={len(candidates)} filtered={len(filtered)}")

        # 후보 리스트 임베드
        desc_lines = []
        for c in filtered:
            sig_str = ", ".join(c["signals"])
            desc_lines.append(
                f"**{c['score']}점** {c['name']} (`{c['ticker']}`) "
                f"— {c['price']:,}원 ({c['prdy_ctrt']:+.1f}%) | {sig_str}"
            )
        score_embed = discord.Embed(
            title=f"🏆 멀티시그널 후보 TOP {len(filtered)}",
            description="\n".join(desc_lines),
            color=0x0066FF,
        )
        score_embed.set_footer(text=mode_label)
        await scoring_msg.edit(content=None, embed=score_embed)

        # ── 2) 상위 후보 순차 AI 분석 → BUY만 수집 ──
        buy_targets: list[dict] = []
        analyzed_count = 0
        analysis_candidates = filtered[:DAY_TRADE_PICKS]
        for c in analysis_candidates:

            analyzed_count += 1
            progress = await channel.send(
                f"🔍 [{analyzed_count}/{len(analysis_candidates)}] "
                f"**{c['name']}** (`{c['ticker']}`) AI 분석 중… (약 3~5분)"
            )
            try:
                ta = TradingAgentsGraph(debug=False, config=config)
                analysis_symbol = _yf_ticker(c["ticker"], reference_price=c["price"])
                final_state, decision = await loop.run_in_executor(
                    None, ta.propagate, analysis_symbol, trade_date
                )
                emoji = "🟢" if decision == "BUY" else "🔴" if decision == "SELL" else "🟡"
                color_map = {"BUY": 0x00FF00, "SELL": 0xFF0000, "HOLD": 0xFFAA00}
                summary = _extract_decision_summary(final_state, decision, c["ticker"])
                embed = discord.Embed(
                    title=f"{emoji} {c['name']} ({c['ticker']}) → {decision}",
                    description=summary,
                    color=color_map.get(decision.upper(), 0x808080),
                )
                await progress.edit(content=None, embed=embed)

                report_text = _build_report_text(
                    final_state,
                    c["ticker"],
                    market="KR",
                    analysis_symbol=analysis_symbol,
                )
                report_file, report_path = _prepare_report_attachment(
                    report_text,
                    market="KR",
                    ticker=c["ticker"],
                    trade_date=trade_date,
                    scope="AUTO_KR",
                )
                if AUTO_REPORT_UPLOAD:
                    try:
                        await channel.send(file=report_file)
                    except Exception as e:
                        _log(
                            "WARN",
                            "AUTO_BUY_REPORT_UPLOAD_FAIL",
                            f"ticker={c['ticker']} error={str(e)[:160]} path={report_path or 'N/A'}",
                        )
                        await channel.send(
                            "⚠️ 보고서 파일 업로드에 실패했습니다. "
                            + (f"로컬 저장 파일: `{report_path}`" if report_path else "로컬 저장도 실패했습니다.")
                        )

                if decision.upper() == "BUY":
                    buy_targets.append({
                        "ticker": c["ticker"],
                        "name": c["name"],
                        "price": c["price"],
                        "score": c["score"],
                        "signals": c["signals"],
                    })
                _log("INFO", "AUTO_BUY_ANALYZED", f"ticker={c['ticker']} decision={decision}")
            except Exception as e:
                _log("ERROR", "AUTO_BUY_ANALYZE_ERROR", f"ticker={c['ticker']} error={str(e)[:160]}")
                await progress.edit(
                    content=f"❌ {c['name']} 분석 실패: {str(e)[:200]}"
                )

        if not buy_targets:
            _log("INFO", "AUTO_BUY_NO_BUY_TARGET", "분석 완료 후 BUY 대상 없음")
            await channel.send("📋 **AI 분석 완료** — BUY 종목이 없어 매수를 건너뜁니다.")
            return

        # ── 3) 장 열림 대기 → 통장 전액 균등분배 → 자동 매수 ──
        if not await _wait_for_market_open(channel, "KR"):
            _log("INFO", "AUTO_BUY_SKIP", "장 마감 이후라 자동매수 생략")
            await channel.send("❌ 장 마감 이후라 자동매수를 건너뜁니다.")
            return

        try:
            balance_data = await loop.run_in_executor(None, kis.get_balance, "KR")
            cash = balance_data.get("summary", {}).get("cash", 0)
        except Exception as e:
            _log("ERROR", "AUTO_BUY_BALANCE_ERROR", str(e)[:200])
            await channel.send(f"❌ 잔액 조회 실패: {str(e)[:300]}")
            return

        if cash <= 0:
            _log("WARN", "AUTO_BUY_NO_CASH", "예수금 0원")
            await channel.send("❌ 예수금이 0원입니다. 매수할 수 없습니다.")
            return

        budget_info = _compute_auto_buy_budget("KR", cash)
        daily_budget = int(budget_info["usable_budget"])
        if daily_budget <= 0:
            _log("WARN", "AUTO_BUY_NO_BUDGET", f"cash={cash} ratio={budget_info['ratio']}")
            await channel.send("❌ 오늘 사용할 자동매수 예산이 0원이라 매수를 건너뜁니다.")
            return

        per_stock_budget = int(daily_budget // len(buy_targets))
        await channel.send(
            "💸 **KR 자동매수 예산**\n"
            f"가용 예수금: {format_krw(cash)}\n"
            f"기준 자금(anchor): {format_krw(budget_info['anchor'])}\n"
            f"적용 비율: {budget_info['ratio'] * 100:.1f}%\n"
            f"오늘 사용 예산: {format_krw(daily_budget)}"
        )
        buy_results: list[str] = []
        total_invested = 0

        for target in buy_targets:
            # 매수 직전 현재가 재조회
            try:
                current_price = await loop.run_in_executor(None, kis.get_price, target["ticker"], "KR")
            except Exception:
                current_price = target["price"]
            if current_price <= 0:
                buy_results.append(f"⚠️ {target['name']} — 현재가 조회 실패")
                continue

            qty = int(per_stock_budget // current_price)
            if qty <= 0:
                buy_results.append(
                    f"⚠️ {target['name']} — 예산({format_krw(per_stock_budget)}) 부족"
                )
                continue

            # 잔액 재확인
            try:
                fresh_bal = await loop.run_in_executor(None, kis.get_balance, "KR")
                remaining_cash = fresh_bal.get("summary", {}).get("cash", 0)
            except Exception:
                remaining_cash = cash

            remaining_budget = max(daily_budget - total_invested, 0)
            effective_cash = min(remaining_cash, remaining_budget)

            if qty * current_price > effective_cash:
                qty = int(effective_cash // current_price)
                if qty <= 0:
                    buy_results.append(f"⚠️ {target['name']} — 잔액 부족")
                    continue

            try:
                result = await loop.run_in_executor(
                    None, kis.buy_stock, target["ticker"], qty, 0, "KR"
                )
                if result["success"]:
                    amount = qty * current_price
                    total_invested += amount
                    record_trade(
                        target["ticker"], target["name"], "BUY",
                        qty, current_price,
                        order_no=result.get("order_no", ""),
                        reason=f"데이트레이딩 자동매수 (score={target['score']})",
                        market="KR",
                        currency="KRW",
                    )
                    buy_results.append(
                        f"✅ {target['name']} ({target['ticker']}) — "
                        f"{qty}주 × {current_price:,}원 = {format_krw(amount)}"
                    )
                else:
                    buy_results.append(
                        f"❌ {target['name']} 매수실패: {result['message'][:180]}"
                    )
            except Exception as e:
                buy_results.append(f"❌ {target['name']} 매수오류: {str(e)[:180]}")

        # ── 결과 임베드 ──
        result_embed = discord.Embed(
            title=f"🌅 자동매수 결과 ({len(buy_targets)}종목)",
            description="\n".join(buy_results),
            color=0x00FF00,
            timestamp=datetime.datetime.now(KST),
        )
        result_embed.add_field(
            name="투자금액", value=format_krw(total_invested), inline=True
        )
        result_embed.add_field(
            name="예산 잔여", value=format_krw(max(daily_budget - total_invested, 0)), inline=True
        )
        result_embed.add_field(
            name="예수금 잔액", value=format_krw(max(cash - total_invested, 0)), inline=True
        )
        result_embed.set_footer(text=f"데이 트레이딩 | {mode_label}")
        await channel.send(embed=result_embed)

        # 매수 완료 상태 기록 (재시작 시 중복 방지)
        bought_names = ", ".join(t["name"] for t in buy_targets)
        mark_action_done("morning_buy", details=f"매수: {bought_names}")
        _log("INFO", "AUTO_BUY_DONE", f"buy_count={len(buy_targets)} invested={total_invested}")


@morning_auto_buy.before_loop
async def before_morning():
    await bot.wait_until_ready()


# ─── 스케줄: 오후 자동매도 (15:20 KST) ───────────────────


@tasks.loop(time=datetime.time(hour=_sell_h, minute=_sell_m, tzinfo=KST))
async def afternoon_auto_sell():
    """매일 오후(기본 15:20) 워치리스트 외 종목만 전량 매도.

    워치리스트(대형주/ETF)에 포함된 종목은 당일 강제매도하지 않고
    손절/익절 모니터링에만 맡긴다. 스윙 보유를 허용한다.
    """
    if not ALLOWED_CHANNEL_IDS or not kis.is_configured:
        _log("INFO", "AUTO_SELL_SKIP", "채널 미설정 또는 KIS 미설정")
        return
    if not _is_market_day("KR"):
        _log("INFO", "AUTO_SELL_SKIP", "오늘은 휴장일")
        return
    # 재시작 중복 방지: 오늘 이미 매도 완료했으면 스킵
    if is_action_done("afternoon_sell"):
        _log("INFO", "AUTO_SELL_SKIP", "오늘 afternoon_sell 이미 완료")
        return

    channel_id = next(iter(ALLOWED_CHANNEL_IDS))
    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        _log("WARN", "AUTO_SELL_SKIP", f"채널 접근 실패 channel_id={channel_id}")
        return

    mode_label = "🧪 모의투자" if kis.virtual else "💰 실전투자"
    loop = asyncio.get_running_loop()
    _log("INFO", "AUTO_SELL_START", f"time={AUTO_SELL_TIME}")

    await channel.send(
        f"🌇 **오후 매도 점검** 시작 ({AUTO_SELL_TIME} KST)\n"
        f"ℹ️ 워치리스트(대형주/ETF) 종목은 스윙 보유 → 손절/익절만 적용"
    )

    # 보유종목 확인
    try:
        balance_data = await loop.run_in_executor(None, kis.get_balance, "KR")
        holdings = balance_data.get("holdings", [])
    except Exception as e:
        _log("ERROR", "AUTO_SELL_BALANCE_ERROR", str(e)[:200])
        await channel.send(f"❌ 잔고 조회 실패: {str(e)[:300]}")
        return

    if not holdings:
        _log("INFO", "AUTO_SELL_EMPTY", "보유 종목 없음")
        await channel.send("📋 보유 종목이 없습니다. 매도 생략.")
        return

    # 워치리스트 종목은 당일 강제매도에서 제외
    kr_watchlist_set = set(kis.kr_watchlist)
    sell_holdings = [h for h in holdings if h["ticker"] not in kr_watchlist_set]
    keep_holdings = [h for h in holdings if h["ticker"] in kr_watchlist_set]

    if keep_holdings:
        keep_names = ", ".join(f"{h['name']}({h['ticker']})" for h in keep_holdings)
        await channel.send(
            f"🏦 **스윙 보유 유지** ({len(keep_holdings)}종목): {keep_names}\n"
            f"→ 손절({STOP_LOSS_PCT}%)/익절({TAKE_PROFIT_PCT}%) 모니터링만 적용"
        )
        _log("INFO", "AUTO_SELL_KEEP_WATCHLIST", f"keep={len(keep_holdings)} tickers={keep_names}")

    if not sell_holdings:
        _log("INFO", "AUTO_SELL_ALL_WATCHLIST", "전종목이 워치리스트 → 매도 생략")
        await channel.send("📋 **워치리스트 외 매도 대상이 없습니다.** 전종목 스윙 보유.")
        mark_action_done("afternoon_sell", details="전종목 워치리스트 보유")
        return

    _log("INFO", "AUTO_SELL_HOLDINGS", f"total={len(holdings)} sell={len(sell_holdings)} keep={len(keep_holdings)}")

    # 워치리스트 외 종목만 전량 매도
    sell_results = []
    for h in sell_holdings:
        try:
            result = await loop.run_in_executor(
                None, kis.sell_stock, h["ticker"], h["qty"], 0, "KR"
            )
            sell_results.append({
                "success": result["success"],
                "ticker": h["ticker"],
                "name": h["name"],
                "qty": h["qty"],
                "avg_price": h.get("avg_price", 0),
                "sell_price": h.get("current_price", 0),
                "order_no": result.get("order_no", ""),
                "message": result.get("message", ""),
            })
        except Exception as e:
            sell_results.append({
                "success": False,
                "ticker": h["ticker"],
                "name": h["name"],
                "qty": h["qty"],
                "avg_price": h.get("avg_price", 0),
                "sell_price": 0,
                "order_no": "",
                "message": str(e)[:200],
            })

    # DB 기록 + 임베드 작성
    result_lines: list[str] = []
    total_pnl = 0
    total_invested = 0
    total_recovered = 0

    for sr in sell_results:
        if sr["success"]:
            record_trade(
                sr["ticker"], sr["name"], "SELL",
                sr["qty"], sr["sell_price"],
                order_no=sr.get("order_no", ""),
                reason="데이트레이딩 자동매도",
                market="KR",
                currency="KRW",
            )
            if sr["avg_price"] > 0 and sr["sell_price"] > 0:
                record_pnl(
                    sr["ticker"], sr["name"],
                    sr["avg_price"], sr["sell_price"], sr["qty"],
                    market="KR",
                    currency="KRW",
                )
            pnl = (sr["sell_price"] - sr["avg_price"]) * sr["qty"]
            pnl_rate = (
                (sr["sell_price"] - sr["avg_price"]) / sr["avg_price"] * 100
                if sr["avg_price"] > 0 else 0
            )
            invested = sr["avg_price"] * sr["qty"]
            recovered = sr["sell_price"] * sr["qty"]
            total_pnl += pnl
            total_invested += invested
            total_recovered += recovered
            emoji = "🟢" if pnl >= 0 else "🔴"
            result_lines.append(
                f"{emoji} **{sr['name']}** (`{sr['ticker']}`) — "
                f"{sr['qty']}주 | {_format_money(sr['avg_price'], 'KRW')}→"
                f"{_format_money(sr['sell_price'], 'KRW')} | "
                f"{_format_money(pnl, 'KRW')} ({pnl_rate:+.1f}%)"
            )
        else:
            result_lines.append(
                f"❌ **{sr['name']}** (`{sr['ticker']}`) 매도실패: {sr['message'][:80]}"
            )

    # 실패한 종목 1회 재시도
    failed = [sr for sr in sell_results if not sr["success"]]
    if failed:
        await channel.send(f"⚠️ 매도 실패 {len(failed)}건 — 60초 후 재시도…")
        await asyncio.sleep(60)
        for sr in failed:
            try:
                retry = await loop.run_in_executor(
                    None, kis.sell_stock, sr["ticker"], sr["qty"], 0, "KR"
                )
                if retry["success"]:
                    try:
                        sp = await loop.run_in_executor(None, kis.get_price, sr["ticker"], "KR")
                    except Exception:
                        sp = 0
                    record_trade(
                        sr["ticker"], sr["name"], "SELL", sr["qty"], sp,
                        order_no=retry.get("order_no", ""),
                        reason="데이트레이딩 재시도매도",
                        market="KR",
                        currency="KRW",
                    )
                    if sr["avg_price"] > 0 and sp > 0:
                        record_pnl(
                            sr["ticker"],
                            sr["name"],
                            sr["avg_price"],
                            sp,
                            sr["qty"],
                            market="KR",
                            currency="KRW",
                        )
                    pnl = (sp - sr["avg_price"]) * sr["qty"]
                    result_lines.append(
                        f"✅ [재시도 성공] {sr['name']} — {_format_money(pnl, 'KRW')}"
                    )
                    total_pnl += pnl
                else:
                    result_lines.append(
                        f"❌ [재시도 실패] {sr['name']}: {retry['message'][:80]}"
                    )
            except Exception as e:
                result_lines.append(
                    f"❌ [재시도 오류] {sr['name']}: {str(e)[:80]}"
                )

    # 일일 손익 요약 임베드
    pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
    cumulative = get_total_pnl(currency="KRW")

    sell_embed = discord.Embed(
        title="🌇 오후 매도 결과 (워치리스트 외 종목)",
        description="\n".join(result_lines) if result_lines else "매도 대상 없음",
        color=0x00FF00 if total_pnl >= 0 else 0xFF0000,
        timestamp=datetime.datetime.now(KST),
    )
    sell_embed.add_field(
        name=f"{pnl_emoji} 오늘 손익", value=_format_money(total_pnl, "KRW"), inline=True
    )
    sell_embed.add_field(
        name="투입금액", value=_format_money(total_invested, "KRW"), inline=True
    )
    sell_embed.add_field(
        name="회수금액", value=_format_money(total_recovered, "KRW"), inline=True
    )
    sell_embed.add_field(
        name="📊 누적 손익",
        value=f"{_format_money(cumulative['total_pnl'], 'KRW')} | 승률 {cumulative['win_rate']}%",
        inline=False,
    )
    sell_embed.set_footer(text=f"대형주+ETF 전략 | {mode_label}")
    await channel.send(embed=sell_embed)

    # 매도 완료 상태 기록 (재시작 시 중복 방지)
    mark_action_done("afternoon_sell", details=f"매도={len(sell_results)} 보유유지={len(keep_holdings)}")
    _log("INFO", "AUTO_SELL_DONE", f"sold={len(sell_results)} kept={len(keep_holdings)} total_pnl={total_pnl}")


@afternoon_auto_sell.before_loop
async def before_afternoon():
    await bot.wait_until_ready()


# ─── 스케줄: 미국 자동매수 (09:35 ET) ───────────────────────
@tasks.loop(time=datetime.time(hour=_us_buy_h, minute=_us_buy_m, tzinfo=NY_TZ))
async def us_morning_auto_buy():
    """매일 오전(미국 현지) 상위 후보 분석 후 자동 매수."""
    if not ENABLE_US_TRADING or not kis.enable_us_trading:
        return
    if not ALLOWED_CHANNEL_IDS or not kis.is_configured:
        _log("INFO", "US_AUTO_BUY_SKIP", "채널 미설정 또는 KIS 미설정")
        return
    if not _is_market_day("US"):
        _log("INFO", "US_AUTO_BUY_SKIP", "오늘은 미국시장 휴장일")
        return
    if _analysis_lock.locked():
        _log("INFO", "US_AUTO_BUY_SKIP", "analysis lock 사용 중")
        return
    if is_action_done("us_morning_buy"):
        _log("INFO", "US_AUTO_BUY_SKIP", "오늘 us_morning_buy 이미 완료")
        return

    channel_id = next(iter(ALLOWED_CHANNEL_IDS))
    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        _log("WARN", "US_AUTO_BUY_SKIP", f"채널 접근 실패 channel_id={channel_id}")
        return

    trade_date = str(datetime.datetime.now(NY_TZ).date())
    mode_label = "🧪 모의투자" if kis.virtual else "💰 실전투자"
    loop = asyncio.get_running_loop()

    async with _analysis_lock:
        _log("INFO", "US_AUTO_BUY_START", f"date={trade_date} target_picks={US_DAY_TRADE_PICKS}")
        await channel.send(
            f"🇺🇸🌅 **미국 자동매수** 시작 ({US_AUTO_BUY_TIME} ET)"
        )

        try:
            scoring_msg = await channel.send("📊 미국 워치리스트(대형주+ETF) 스코어링 중…")
            candidates = await _compute_us_stock_scores(count=max(10, US_DAY_TRADE_PICKS * 2))
        except Exception as e:
            _log("ERROR", "US_AUTO_BUY_SCORING_ERROR", str(e)[:200])
            await channel.send(f"❌ 미국 후보 조회 실패: {str(e)[:300]}")
            return

        if not candidates:
            _log("INFO", "US_AUTO_BUY_NO_CANDIDATE", "후보 없음")
            await scoring_msg.edit(content="❌ 미국 매수 후보가 없습니다.")
            return

        try:
            balance_data = await loop.run_in_executor(None, kis.get_balance, "US")
            held_tickers = {h["ticker"] for h in balance_data.get("holdings", [])}
        except Exception:
            held_tickers = set()

        filtered = [c for c in candidates if c["ticker"] not in held_tickers]
        if not filtered:
            await scoring_msg.edit(content="📋 후보 종목이 모두 이미 보유 중입니다.")
            return

        desc_lines = []
        for c in filtered:
            sig_str = ", ".join(c["signals"])
            desc_lines.append(
                f"**{c['score']}점** {c['name']} (`{c['ticker']}`) "
                f"— {_format_money(c['price'], 'USD')} ({c['prdy_ctrt']:+.2f}%) | {sig_str}"
            )
        score_embed = discord.Embed(
            title=f"🇺🇸 워치리스트 후보 TOP {len(filtered)}",
            description="\n".join(desc_lines),
            color=0x0066FF,
            timestamp=datetime.datetime.now(NY_TZ),
        )
        score_embed.set_footer(text=f"{mode_label} | USD")
        await scoring_msg.edit(content=None, embed=score_embed)

        buy_targets: list[dict] = []
        analyzed_count = 0
        analysis_candidates = filtered[:US_DAY_TRADE_PICKS]
        for c in analysis_candidates:
            analyzed_count += 1
            progress = await channel.send(
                f"🔍 [{analyzed_count}/{len(analysis_candidates)}] "
                f"**{c['name']}** (`{c['ticker']}`) AI 분석 중…"
            )
            try:
                ta = TradingAgentsGraph(debug=False, config=config)
                final_state, decision = await loop.run_in_executor(
                    None, ta.propagate, c["ticker"], trade_date
                )
                emoji = "🟢" if decision == "BUY" else "🔴" if decision == "SELL" else "🟡"
                color_map = {"BUY": 0x00FF00, "SELL": 0xFF0000, "HOLD": 0xFFAA00}
                summary = _extract_decision_summary(final_state, decision, c["ticker"], "US")
                embed = discord.Embed(
                    title=f"{emoji} {c['name']} ({c['ticker']}) → {decision}",
                    description=summary,
                    color=color_map.get(decision.upper(), 0x808080),
                )
                await progress.edit(content=None, embed=embed)

                report_text = _build_report_text(
                    final_state,
                    c["ticker"],
                    market="US",
                    analysis_symbol=c["ticker"],
                )
                report_file, report_path = _prepare_report_attachment(
                    report_text,
                    market="US",
                    ticker=c["ticker"],
                    trade_date=trade_date,
                    scope="AUTO_US",
                )
                if AUTO_REPORT_UPLOAD:
                    try:
                        await channel.send(file=report_file)
                    except Exception as e:
                        _log(
                            "WARN",
                            "US_AUTO_BUY_REPORT_UPLOAD_FAIL",
                            f"ticker={c['ticker']} error={str(e)[:160]} path={report_path or 'N/A'}",
                        )
                        await channel.send(
                            "⚠️ 보고서 파일 업로드에 실패했습니다. "
                            + (f"로컬 저장 파일: `{report_path}`" if report_path else "로컬 저장도 실패했습니다.")
                        )

                if decision.upper() == "BUY":
                    buy_targets.append(c)
                _log("INFO", "US_AUTO_BUY_ANALYZED", f"ticker={c['ticker']} decision={decision}")
            except Exception as e:
                _log("ERROR", "US_AUTO_BUY_ANALYZE_ERROR", f"ticker={c['ticker']} error={str(e)[:160]}")
                await progress.edit(content=f"❌ {c['name']} 분석 실패: {str(e)[:200]}")

        if not buy_targets:
            await channel.send("📋 **미국 AI 분석 완료** — BUY 종목이 없어 매수를 건너뜁니다.")
            return

        if not await _wait_for_market_open(channel, "US"):
            _log("INFO", "US_AUTO_BUY_SKIP", "미국 장 마감 이후라 자동매수 생략")
            await channel.send("❌ 미국 장 마감 이후라 자동매수를 건너뜁니다.")
            return

        try:
            balance_data = await loop.run_in_executor(None, kis.get_balance, "US")
            cash = balance_data.get("summary", {}).get("USD", {}).get("cash", 0)
        except Exception as e:
            _log("ERROR", "US_AUTO_BUY_BALANCE_ERROR", str(e)[:200])
            await channel.send(f"❌ USD 잔액 조회 실패: {str(e)[:300]}")
            return

        if cash <= 0:
            await channel.send("❌ USD 예수금이 0입니다. 매수를 건너뜁니다.")
            return

        budget_info = _compute_auto_buy_budget("US", cash)
        daily_budget = float(budget_info["usable_budget"])
        if daily_budget <= 0:
            _log("WARN", "US_AUTO_BUY_NO_BUDGET", f"cash={cash} ratio={budget_info['ratio']}")
            await channel.send("❌ 오늘 사용할 미국 자동매수 예산이 0이라 매수를 건너뜁니다.")
            return

        per_stock_budget = float(daily_budget) / len(buy_targets)
        await channel.send(
            "💸 **US 자동매수 예산**\n"
            f"가용 예수금: {_format_money(cash, 'USD')}\n"
            f"기준 자금(anchor): {_format_money(budget_info['anchor'], 'USD')}\n"
            f"적용 비율: {budget_info['ratio'] * 100:.1f}%\n"
            f"오늘 사용 예산: {_format_money(daily_budget, 'USD')}"
        )
        buy_results: list[str] = []
        total_invested = 0.0

        for target in buy_targets:
            try:
                current_price = await loop.run_in_executor(None, kis.get_price, target["ticker"], "US")
            except Exception:
                current_price = target["price"]
            if current_price <= 0:
                buy_results.append(f"⚠️ {target['name']} — 현재가 조회 실패")
                continue

            qty = int(per_stock_budget // current_price)
            if qty <= 0:
                buy_results.append(
                    f"⚠️ {target['name']} — 예산({_format_money(per_stock_budget, 'USD')}) 부족"
                )
                continue

            try:
                fresh_bal = await loop.run_in_executor(None, kis.get_balance, "US")
                remaining_cash = fresh_bal.get("summary", {}).get("USD", {}).get("cash", cash)
            except Exception:
                remaining_cash = cash

            remaining_budget = max(daily_budget - total_invested, 0.0)
            effective_cash = min(remaining_cash, remaining_budget)

            if qty * current_price > effective_cash:
                qty = int(effective_cash // current_price)
                if qty <= 0:
                    buy_results.append(f"⚠️ {target['name']} — 잔액 부족")
                    continue

            try:
                result = await loop.run_in_executor(None, kis.buy_stock, target["ticker"], qty, 0, "US")
                if result["success"]:
                    amount = qty * current_price
                    total_invested += amount
                    record_trade(
                        target["ticker"],
                        target["name"],
                        "BUY",
                        qty,
                        current_price,
                        order_no=result.get("order_no", ""),
                        reason=f"미국 자동매수 (score={target['score']})",
                        market="US",
                        currency="USD",
                    )
                    buy_results.append(
                        f"✅ {target['name']} ({target['ticker']}) — "
                        f"{qty}주 × {_format_money(current_price, 'USD')} = {_format_money(amount, 'USD')}"
                    )
                else:
                    buy_results.append(f"❌ {target['name']} 매수실패: {result['message'][:180]}")
            except Exception as e:
                buy_results.append(f"❌ {target['name']} 매수오류: {str(e)[:180]}")

        result_embed = discord.Embed(
            title=f"🇺🇸🌅 자동매수 결과 ({len(buy_targets)}종목)",
            description="\n".join(buy_results),
            color=0x00FF00,
            timestamp=datetime.datetime.now(NY_TZ),
        )
        result_embed.add_field(name="투자금액", value=_format_money(total_invested, "USD"), inline=True)
        result_embed.add_field(
            name="예산 잔여",
            value=_format_money(max(daily_budget - total_invested, 0), "USD"),
            inline=True,
        )
        result_embed.add_field(
            name="예수금 잔액",
            value=_format_money(max(cash - total_invested, 0), "USD"),
            inline=True,
        )
        result_embed.set_footer(text=f"미국 대형주+ETF 전략 | {mode_label}")
        await channel.send(embed=result_embed)

        bought_names = ", ".join(t["name"] for t in buy_targets)
        mark_action_done("us_morning_buy", details=f"매수: {bought_names}")
        _log("INFO", "US_AUTO_BUY_DONE", f"buy_count={len(buy_targets)} invested={total_invested}")


@us_morning_auto_buy.before_loop
async def before_us_morning():
    await bot.wait_until_ready()


# ─── 스케줄: 미국 자동매도 (15:50 ET) ───────────────────────
@tasks.loop(time=datetime.time(hour=_us_sell_h, minute=_us_sell_m, tzinfo=NY_TZ))
async def us_afternoon_auto_sell():
    """매일 오후(미국 현지) 워치리스트 외 종목만 전량 매도.

    워치리스트(대형주/ETF)에 포함된 종목은 당일 강제매도하지 않고
    손절/익절 모니터링에만 맡긴다. 스윙 보유를 허용한다.
    """
    if not ENABLE_US_TRADING or not kis.enable_us_trading:
        return
    if not ALLOWED_CHANNEL_IDS or not kis.is_configured:
        _log("INFO", "US_AUTO_SELL_SKIP", "채널 미설정 또는 KIS 미설정")
        return
    if not _is_market_day("US"):
        _log("INFO", "US_AUTO_SELL_SKIP", "미국시장 휴장일")
        return
    if not _is_market_open_now("US"):
        _log("INFO", "US_AUTO_SELL_SKIP", "미국 장시간 아님")
        return
    if is_action_done("us_afternoon_sell"):
        _log("INFO", "US_AUTO_SELL_SKIP", "오늘 us_afternoon_sell 이미 완료")
        return

    channel_id = next(iter(ALLOWED_CHANNEL_IDS))
    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        _log("WARN", "US_AUTO_SELL_SKIP", f"채널 접근 실패 channel_id={channel_id}")
        return

    mode_label = "🧪 모의투자" if kis.virtual else "💰 실전투자"
    loop = asyncio.get_running_loop()
    _log("INFO", "US_AUTO_SELL_START", f"time={US_AUTO_SELL_TIME}")

    await channel.send(
        f"🇺🇸🌇 **미국 오후 매도 점검** 시작 ({US_AUTO_SELL_TIME} ET)\n"
        f"ℹ️ 워치리스트(대형주/ETF) 종목은 스윙 보유 → 손절/익절만 적용"
    )

    try:
        balance_data = await loop.run_in_executor(None, kis.get_balance, "US")
        holdings = balance_data.get("holdings", [])
    except Exception as e:
        _log("ERROR", "US_AUTO_SELL_BALANCE_ERROR", str(e)[:200])
        await channel.send(f"❌ 미국 잔고 조회 실패: {str(e)[:300]}")
        return

    if not holdings:
        await channel.send("📋 미국 보유 종목이 없습니다. 매도 생략.")
        return

    us_watchlist_set = set(kis.us_watchlist)
    sell_holdings = [h for h in holdings if h["ticker"] not in us_watchlist_set]
    keep_holdings = [h for h in holdings if h["ticker"] in us_watchlist_set]

    if keep_holdings:
        keep_names = ", ".join(f"{h['name']}({h['ticker']})" for h in keep_holdings)
        await channel.send(
            f"🏦 **미국 스윙 보유 유지** ({len(keep_holdings)}종목): {keep_names}\n"
            f"→ 손절({STOP_LOSS_PCT}%)/익절({TAKE_PROFIT_PCT}%) 모니터링만 적용"
        )
        _log("INFO", "US_AUTO_SELL_KEEP_WATCHLIST", f"keep={len(keep_holdings)} tickers={keep_names}")

    if not sell_holdings:
        await channel.send("📋 **미국 워치리스트 외 매도 대상이 없습니다.** 전종목 스윙 보유.")
        mark_action_done("us_afternoon_sell", details="전종목 워치리스트 보유")
        return

    sell_results = []
    for h in sell_holdings:
        try:
            result = await loop.run_in_executor(
                None, kis.sell_stock, h["ticker"], h["qty"], 0, "US"
            )
            sell_results.append({
                "success": result["success"],
                "ticker": h["ticker"],
                "name": h["name"],
                "qty": h["qty"],
                "avg_price": h.get("avg_price", 0),
                "sell_price": h.get("current_price", 0),
                "order_no": result.get("order_no", ""),
                "message": result.get("message", ""),
            })
        except Exception as e:
            sell_results.append({
                "success": False,
                "ticker": h["ticker"],
                "name": h["name"],
                "qty": h["qty"],
                "avg_price": h.get("avg_price", 0),
                "sell_price": 0,
                "order_no": "",
                "message": str(e)[:200],
            })

    result_lines: list[str] = []
    total_pnl = 0.0
    total_invested = 0.0
    total_recovered = 0.0

    for sr in sell_results:
        if sr["success"]:
            record_trade(
                sr["ticker"],
                sr["name"],
                "SELL",
                sr["qty"],
                sr["sell_price"],
                order_no=sr.get("order_no", ""),
                reason="미국 오후 자동매도",
                market="US",
                currency="USD",
            )
            if sr["avg_price"] > 0 and sr["sell_price"] > 0:
                record_pnl(
                    sr["ticker"],
                    sr["name"],
                    sr["avg_price"],
                    sr["sell_price"],
                    sr["qty"],
                    market="US",
                    currency="USD",
                )
            pnl = (sr["sell_price"] - sr["avg_price"]) * sr["qty"]
            pnl_rate = (
                (sr["sell_price"] - sr["avg_price"]) / sr["avg_price"] * 100
                if sr["avg_price"] > 0 else 0
            )
            invested = sr["avg_price"] * sr["qty"]
            recovered = sr["sell_price"] * sr["qty"]
            total_pnl += pnl
            total_invested += invested
            total_recovered += recovered
            emoji = "🟢" if pnl >= 0 else "🔴"
            result_lines.append(
                f"{emoji} **{sr['name']}** (`{sr['ticker']}`) — "
                f"{sr['qty']}주 | {_format_money(sr['avg_price'], 'USD')}→{_format_money(sr['sell_price'], 'USD')} | "
                f"{_format_money(pnl, 'USD')} ({pnl_rate:+.1f}%)"
            )
        else:
            result_lines.append(f"❌ **{sr['name']}** (`{sr['ticker']}`) 매도실패: {sr['message'][:80]}")

    failed = [sr for sr in sell_results if not sr["success"]]
    if failed:
        await channel.send(f"⚠️ 미국 매도 실패 {len(failed)}건 — 60초 후 재시도…")
        await asyncio.sleep(60)
        for sr in failed:
            try:
                retry = await loop.run_in_executor(None, kis.sell_stock, sr["ticker"], sr["qty"], 0, "US")
                if retry["success"]:
                    try:
                        sp = await loop.run_in_executor(None, kis.get_price, sr["ticker"], "US")
                    except Exception:
                        sp = 0
                    record_trade(
                        sr["ticker"],
                        sr["name"],
                        "SELL",
                        sr["qty"],
                        sp,
                        order_no=retry.get("order_no", ""),
                        reason="미국 재시도매도",
                        market="US",
                        currency="USD",
                    )
                    if sr["avg_price"] > 0 and sp > 0:
                        record_pnl(
                            sr["ticker"],
                            sr["name"],
                            sr["avg_price"],
                            sp,
                            sr["qty"],
                            market="US",
                            currency="USD",
                        )
                    pnl = (sp - sr["avg_price"]) * sr["qty"]
                    result_lines.append(f"✅ [재시도 성공] {sr['name']} — {_format_money(pnl, 'USD')}")
                    total_pnl += pnl
                else:
                    result_lines.append(f"❌ [재시도 실패] {sr['name']}: {retry['message'][:80]}")
            except Exception as e:
                result_lines.append(f"❌ [재시도 오류] {sr['name']}: {str(e)[:80]}")

    cumulative = get_total_pnl(currency="USD")
    pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
    sell_embed = discord.Embed(
        title="🇺🇸🌇 오후 매도 결과 (워치리스트 외 종목)",
        description="\n".join(result_lines) if result_lines else "매도 대상 없음",
        color=0x00FF00 if total_pnl >= 0 else 0xFF0000,
        timestamp=datetime.datetime.now(NY_TZ),
    )
    sell_embed.add_field(name=f"{pnl_emoji} 오늘 손익", value=_format_money(total_pnl, "USD"), inline=True)
    sell_embed.add_field(name="투입금액", value=_format_money(total_invested, "USD"), inline=True)
    sell_embed.add_field(name="회수금액", value=_format_money(total_recovered, "USD"), inline=True)
    sell_embed.add_field(
        name="📊 USD 누적 손익",
        value=f"{_format_money(cumulative['total_pnl'], 'USD')} | 승률 {cumulative['win_rate']}%",
        inline=False,
    )
    sell_embed.set_footer(text=f"미국 대형주+ETF 전략 | {mode_label}")
    await channel.send(embed=sell_embed)

    mark_action_done("us_afternoon_sell", details=f"매도={len(sell_results)} 보유유지={len(keep_holdings)}")
    _log("INFO", "US_AUTO_SELL_DONE", f"sold={len(sell_results)} kept={len(keep_holdings)} total_pnl={total_pnl}")


@us_afternoon_auto_sell.before_loop
async def before_us_afternoon():
    await bot.wait_until_ready()


# ─── 스케줄: 보유종목 손절/익절 모니터링 ─────────────────
@tasks.loop(minutes=MONITOR_INTERVAL_MIN)
async def monitor_holdings():
    """보유종목 수익률 감시 → 손절/익절 라인 도달 시 자동 매도."""
    if not ALLOWED_CHANNEL_IDS or not kis.is_configured:
        return
    if not _is_market_day("KR") and not _is_market_day("US"):
        return

    channel_id = next(iter(ALLOWED_CHANNEL_IDS))
    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return

    try:
        loop = asyncio.get_running_loop()
        balance_data = await loop.run_in_executor(None, kis.get_balance)
        holdings = balance_data["holdings"]
    except Exception:
        return

    if holdings:
        _log("INFO", "MONITOR_SCAN", f"holdings={len(holdings)}")

    mode_label = "🧪 모의투자" if kis.virtual else "💰 실전투자"

    for h in holdings:
        rate = h["pnl_rate"]
        market = h.get("market", _market_of_ticker(h["ticker"]))
        if not _is_market_open_now(market):
            continue
        triggered = False
        title = ""
        desc_extra = ""

        if rate <= STOP_LOSS_PCT:
            triggered = True
            title = f"🚨 손절 자동매도: {h['name']} ({market})"
            desc_extra = f"⚠️ 손절 라인({STOP_LOSS_PCT}%) 도달 → 자동 시장가 매도"
        elif rate >= TAKE_PROFIT_PCT:
            triggered = True
            title = f"🎉 익절 자동매도: {h['name']} ({market})"
            desc_extra = f"✅ 익절 라인({TAKE_PROFIT_PCT}%) 도달 → 자동 시장가 매도"

        if not triggered:
            continue

        # 재시작 중복 방지: 이 종목 오늘 이미 손절/익절 했으면 스킵
        sl_action = f"stop_loss_{market}_{h['ticker']}"
        if is_action_done(sl_action):
            _log("INFO", "MONITOR_SKIP_DONE", f"ticker={h['ticker']} already_triggered_today")
            continue

        # 자동 매도 실행
        try:
            result = await loop.run_in_executor(
                None, kis.sell_stock, h["ticker"], h["qty"], 0, market
            )
            if result["success"]:
                mark_action_done(sl_action, details=f"{rate:+.1f}%")
                try:
                    sell_price = await loop.run_in_executor(None, kis.get_price, h["ticker"], market)
                except Exception:
                    sell_price = h["current_price"]
                record_trade(
                    h["ticker"], h["name"], "SELL", h["qty"], sell_price,
                    order_no=result.get("order_no", ""),
                    reason=f"손절/익절 자동매도 ({rate:+.1f}%)",
                    market=market,
                    currency=h.get("currency", _currency_of_market(market)),
                )
                if h["avg_price"] > 0 and sell_price > 0:
                    record_pnl(
                        h["ticker"],
                        h["name"],
                        h["avg_price"],
                        sell_price,
                        h["qty"],
                        market=market,
                        currency=h.get("currency", _currency_of_market(market)),
                    )
                currency = h.get("currency", _currency_of_market(market))
                embed = discord.Embed(
                    title=title,
                    description=(
                        f"**시장:** {market}\n"
                        f"**종목:** {h['name']} (`{h['ticker']}`)\n"
                        f"**매도:** {h['qty']}주 × {_format_money(sell_price, currency)}\n"
                        f"**손익:** {_format_money(h['pnl'], currency)} ({rate:+.2f}%)\n\n"
                        f"{desc_extra}"
                    ),
                    color=0xFF0000 if rate < 0 else 0x00FF00,
                )
                embed.set_footer(text=f"{mode_label} | {currency}")
                await channel.send(embed=embed)
                _log(
                    "INFO",
                    "MONITOR_SELL_DONE",
                    f"market={market} ticker={h['ticker']} qty={h['qty']} rate={rate:+.2f}%",
                )
            else:
                _log("WARN", "MONITOR_SELL_FAIL", f"ticker={h['ticker']} message={result['message'][:120]}")
                await channel.send(
                    f"❌ {h['name']} 자동매도 실패: {result['message'][:200]}"
                )
        except Exception as e:
            _log("ERROR", "MONITOR_SELL_ERROR", f"ticker={h['ticker']} error={str(e)[:160]}")
            await channel.send(
                f"❌ {h['name']} 자동매도 오류: {str(e)[:200]}"
            )


@monitor_holdings.before_loop
async def before_monitor():
    await bot.wait_until_ready()


# ─── Bot Events ────────────────────────────────────────────────
@bot.event
async def on_ready():
    synced = await tree.sync()
    if not morning_auto_buy.is_running():
        morning_auto_buy.start()
    if not afternoon_auto_sell.is_running():
        afternoon_auto_sell.start()
    if ENABLE_US_TRADING and not us_morning_auto_buy.is_running():
        us_morning_auto_buy.start()
    if ENABLE_US_TRADING and not us_afternoon_auto_sell.is_running():
        us_afternoon_auto_sell.start()
    if not monitor_holdings.is_running():
        monitor_holdings.start()
    print(f"✅ {bot.user} 로그인 완료! (v{BOT_VERSION})")
    print(f"   서버 수: {len(bot.guilds)}")
    print(f"   동기화된 슬래시 명령 수: {len(synced)}")
    print("   슬래시 명령: /분석, /대형주, /잔고, /매수, /매도, /상태, /봇정보, /스코어링, /스코어규칙, /수익, /수익초기화")
    print(f"   KIS: {'✅ 설정됨' if kis.is_configured else '❌ 미설정'}")
    print(f"   모드: {'🧪 모의투자' if kis.virtual else '💰 실전투자'}")
    print(f"   KR 자동매매: 매수 {AUTO_BUY_TIME} / 매도 {AUTO_SELL_TIME} KST")
    print(f"   KR 매수 종목 수: {DAY_TRADE_PICKS}개 | 예산 비율: {AUTO_BUY_BUDGET_RATIO * 100:.1f}%")
    if ENABLE_US_TRADING:
        print(f"   US 자동매매: 매수 {US_AUTO_BUY_TIME} / 매도 {US_AUTO_SELL_TIME} ET")
        print(f"   US 매수 종목 수: {US_DAY_TRADE_PICKS}개 | 예산 비율: {US_AUTO_BUY_BUDGET_RATIO * 100:.1f}%")
    else:
        print("   US 자동매매: 비활성화 (ENABLE_US_TRADING=false)")
    print(f"   손절: {STOP_LOSS_PCT}% | 익절: {TAKE_PROFIT_PCT}%")
    print(f"   모니터링: {MONITOR_INTERVAL_MIN}분 간격")
    if ALLOWED_CHANNEL_IDS:
        print(f"   허용 채널: {ALLOWED_CHANNEL_IDS}")
    else:
        print("   허용 채널: 전체 (제한 없음)")
        print("   ⚠️ 자동매매: DISCORD_CHANNEL_IDS 설정 필요")

    # 디스코드 채널에 버전 알림 전송
    if ALLOWED_CHANNEL_IDS:
        mode_label = "🧪 모의투자" if kis.virtual else "💰 실전투자"
        embed = discord.Embed(
            title=f"🚀 봇 시작됨 — v{BOT_VERSION}",
            color=0x2ECC71,
            timestamp=datetime.datetime.now(KST),
        )
        embed.add_field(name="모드", value=mode_label, inline=True)
        embed.add_field(name="KR 매수", value=f"{AUTO_BUY_TIME} KST", inline=True)
        embed.add_field(name="KR 매도", value=f"{AUTO_SELL_TIME} KST", inline=True)
        if kis.kr_watchlist:
            wl_preview = ", ".join(kis.kr_watchlist[:6])
            if len(kis.kr_watchlist) > 6:
                wl_preview += f" 외 {len(kis.kr_watchlist) - 6}개"
            embed.add_field(name="KR 워치리스트", value=wl_preview, inline=False)
        embed.set_footer(text=f"손절 {STOP_LOSS_PCT}% | 익절 {TAKE_PROFIT_PCT}% | 감시 {MONITOR_INTERVAL_MIN}분")
        for ch_id in ALLOWED_CHANNEL_IDS:
            ch = bot.get_channel(ch_id)
            if isinstance(ch, discord.TextChannel):
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass


# ─── Entry Point ───────────────────────────────────────────────
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
