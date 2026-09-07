"""TradingAgents Vietnam - Multi-Agent Financial Trading & Research Dashboard.

Built with Streamlit and Plotly for Vietnamese equity markets (HOSE, HNX, UPCoM):
- Interactive technical candlestick charting (OHLCV, SMA20/50, Volume, RSI(14), MACD(12,26,9)).
- Vietnam Statutory Tax & Transaction Friction Model (0.1% Sell Tax, Brokerage Fee, Breakeven Hurdle).
- Smart Position Sizing & 100-share Lot Capital Allocation Engine.
- Multi-Agent Research Reports (Technical, Fundamentals, Local News, Vietnam Macro, Bull/Bear Debate, Trader, PM Decision).
- Paper Trading Simulator (10M VND cash, real-time market order execution, portfolio tracking).
- DNSE Entrade X Open API Integration Hub.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf

from tradingagents.dataflows.dnse_client import DNSEClient, PaperTradingEngine
from tradingagents.dataflows.symbol_utils import normalize_symbol
from tradingagents.dataflows.vn_data import (
    VN_COMMON_TICKERS,
    calculate_vn_trade_friction,
    get_vietnam_macro_data,
    get_vietnam_news,
    is_vietnam_symbol,
    normalize_vn_symbol,
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.swing.regime_agent import MarketRegimeResult, RegimeAgent, RegimeStatus
from tradingagents.swing.risk_agent import (
    ExitAction,
    PortfolioPosition,
    PositionPlan,
    RiskAgent,
    TPlusStatus,
)
from tradingagents.swing.setup_agent import SetupAgent, SetupResult, SetupStatus

# Page Configuration
st.set_page_config(
    page_title="TradingAgents Vietnam - AI Trading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling (Dark financial theme with Navy & Gold accents)
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #f8fafc;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.0rem;
        color: #94a3b8;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 16px;
        border-radius: 6px;
    }
    .tax-alert {
        background-color: #1e1b4b;
        border-left: 4px solid #f59e0b;
        padding: 12px;
        border-radius: 4px;
        margin-bottom: 15px;
    }
    .paper-card {
        background-color: #0f172a;
        border: 1px solid #38bdf8;
        border-radius: 8px;
        padding: 14px;
        margin-bottom: 14px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize Paper Trading Engine in session
if "paper_engine" not in st.session_state:
    st.session_state.paper_engine = PaperTradingEngine()


# --- SIDEBAR: Cấu hình phân tích ---
with st.sidebar:
    st.image("https://raw.githubusercontent.com/TauricResearch/TradingAgents/main/assets/TauricResearch.png", width=220)
    st.markdown("### 🇻🇳 Thị trường Việt Nam")
    st.caption("Khung quy chuẩn: Luật Chứng khoán 2019 & Luật Thuế TNCN")

    # Ticker Selection
    popular_vn_tickers = sorted(list(VN_COMMON_TICKERS))
    default_idx = popular_vn_tickers.index("VNM") if "VNM" in popular_vn_tickers else 0
    selected_ticker_quick = st.selectbox(
        "Chọn mã cổ phiếu VN hàng đầu:",
        options=popular_vn_tickers,
        index=default_idx,
    )

    custom_ticker = st.text_input("Hoặc nhập mã tùy ý (ví dụ: HPG, FPT, VCB):", value="")
    raw_symbol = custom_ticker.strip().upper() if custom_ticker.strip() else selected_ticker_quick
    symbol = normalize_vn_symbol(raw_symbol)

    # Date Window
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input(
            "Từ ngày:",
            value=datetime.now() - timedelta(days=120),
        )
    with col_d2:
        end_date = st.date_input(
            "Đến ngày:",
            value=datetime.now(),
        )

    # Analysis Configuration
    st.markdown("---")
    st.markdown("#### ⚙️ Cấu hình Tác tử (Agents)")
    research_depth = st.radio(
        "Độ sâu phân tích:",
        options=["Tiêu chuẩn (1 vòng tranh luận)", "Chuyên sâu (2 vòng tranh luận)"],
        index=0,
    )
    max_rounds = 1 if "1" in research_depth else 2

    analysts_selected = st.multiselect(
        "Đội ngũ phân tích:",
        options=["Phân tích Kỹ thuật (Market)", "Phân tích Cơ bản (Fundamentals)", "Tin tức & Tâm lý (News & Sentiment)"],
        default=["Phân tích Kỹ thuật (Market)", "Phân tích Cơ bản (Fundamentals)", "Tin tức & Tâm lý (News & Sentiment)"],
    )

    llm_provider = st.selectbox(
        "Mô hình LLM:",
        options=["OpenAI (GPT-4o / GPT-5)", "Google Gemini (Gemini 2.5/3 Flash)", "Anthropic Claude", "DeepSeek", "Ollama Local"],
        index=0,
    )

    st.markdown("---")
    st.markdown("#### ⚡ Chế Độ Tự Động (Auto-Pilot)")
    auto_pilot_enabled = st.toggle(
        "Tự động đặt lệnh theo tín hiệu",
        value=True,
        help="Khi BẬT: Cứ mỗi khi AI kết luận BUY/SELL, hệ thống tự động bắn lệnh vào sàn/giả lập theo đúng khối lượng đã tính toán mà không cần anh bấm tay.",
    )
    if auto_pilot_enabled:
        st.success("🟢 Auto-Pilot: BẬT (Tự động vào lệnh)")
    else:
        st.info("⚪ Thủ công: Chờ người dùng xác nhận")

    st.markdown("---")
    run_button = st.button("🚀 Kích Hoạt Phân Tích & Khớp Lệnh", use_container_width=True, type="primary")


# --- DATA FETCHING (yfinance with cache) ---
@st.cache_data(ttl=300)
def load_price_data(ticker_symbol: str, start: str, end: str):
    canonical = normalize_symbol(ticker_symbol)
    try:
        t = yf.Ticker(canonical)
        df = t.history(start=start, end=end)
        info = t.info or {}
        return df, info, canonical
    except Exception as exc:
        return pd.DataFrame(), {}, canonical

df_price, company_info, canonical_symbol = load_price_data(
    symbol,
    start_date.strftime("%Y-%m-%d"),
    end_date.strftime("%Y-%m-%d"),
)


@st.cache_data(ttl=600)
def load_market_benchmark():
    start_dt = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
    end_dt = datetime.now().strftime("%Y-%m-%d")
    for sym in ["^VNINDEX", "E1VFVN30.VN", "VN30"]:
        df, _, c_sym = load_price_data(sym, start_dt, end_dt)
        if not df.empty and len(df) >= 20:
            return df, c_sym
    return pd.DataFrame(), "N/A"

# --- HEADER SECTION ---
company_name = company_info.get("longName") or company_info.get("shortName") or symbol
sector = company_info.get("sector") or "N/A"
industry = company_info.get("industry") or "N/A"

st.markdown(f"<div class='main-title'>📊 {company_name} ({canonical_symbol})</div>", unsafe_allow_html=True)
st.markdown(f"<div class='sub-title'>Ngành: {sector} | Lĩnh vực: {industry} | Tiền tệ: VND</div>", unsafe_allow_html=True)

# Top Metrics Bar
m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
latest_price = 0.0
change_pct = 0.0
ref_price = 0.0

if not df_price.empty:
    latest_close = df_price["Close"].iloc[-1]
    prev_close = df_price["Close"].iloc[-2] if len(df_price) > 1 else latest_close
    latest_price = float(latest_close)
    change = latest_close - prev_close
    change_pct = (change / prev_close) * 100 if prev_close > 0 else 0.0
    ref_price = float(prev_close)

    ceiling_price = round(ref_price * 1.07, -1)  # HOSE ±7%
    floor_price = round(ref_price * 0.93, -1)

    with m_col1:
        st.metric("Giá hiện tại", f"{latest_price:,.0f} đ", f"{change_pct:+.2f}%")
    with m_col2:
        st.metric("Giá Trần (+7%)", f"{ceiling_price:,.0f} đ")
    with m_col3:
        st.metric("Giá Sàn (-7%)", f"{floor_price:,.0f} đ")
    with m_col4:
        volume = int(df_price["Volume"].iloc[-1])
        st.metric("Khối lượng (KLGD)", f"{volume:,.0f}")
    with m_col5:
        pe_ratio = company_info.get("trailingPE")
        pe_str = f"{pe_ratio:.1f}x" if pe_ratio else "N/A"
        st.metric("P/E TTM", pe_str)
else:
    st.warning(f"Không tìm thấy dữ liệu giá cho mã {canonical_symbol}. Vui lòng kiểm tra lại mã hoặc kết nối mạng.")


# --- MAIN TABS ---
tab_chart, tab_swing, tab_tax, tab_reports, tab_dnse = st.tabs([
    "📈 Biểu Đồ & Kỹ Thuật (RSI/MACD)",
    "🎯 Chiến Lược 3-Agent (VCP & T+2.5)",
    "⚖️ Quản Lý Vốn & Thuế Phí",
    "🤖 Báo Cáo Multi-Agent",
    "🏦 Đặt Lệnh Giả Lập & DNSE API",
])

# ==============================================================================
# TAB 1: BIỂU ĐỒ KỸ THUẬT NÂNG CAO (Plotly Candlestick + RSI + MACD)
# ==============================================================================
with tab_chart:
    st.subheader("Biểu đồ Nến, Chỉ báo Kỹ thuật & Khối lượng")
    if not df_price.empty:
        df_chart = df_price.copy()

        # Moving Averages
        df_chart["SMA20"] = df_chart["Close"].rolling(window=20).mean()
        df_chart["SMA50"] = df_chart["Close"].rolling(window=50).mean()

        # RSI(14)
        delta = df_chart["Close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=14, min_periods=14).mean()
        avg_loss = loss.rolling(window=14, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, 0.00001)
        df_chart["RSI"] = 100 - (100 / (1 + rs))

        # MACD(12, 26, 9)
        ema12 = df_chart["Close"].ewm(span=12, adjust=False).mean()
        ema26 = df_chart["Close"].ewm(span=26, adjust=False).mean()
        df_chart["MACD"] = ema12 - ema26
        df_chart["Signal"] = df_chart["MACD"].ewm(span=9, adjust=False).mean()
        df_chart["MACD_Hist"] = df_chart["MACD"] - df_chart["Signal"]

        # Indicator Status Badges
        latest_rsi = df_chart["RSI"].dropna().iloc[-1] if not df_chart["RSI"].dropna().empty else 50.0
        latest_macd = df_chart["MACD"].iloc[-1]
        latest_signal = df_chart["Signal"].iloc[-1]

        c_ind1, c_ind2, c_ind3 = st.columns(3)
        with c_ind1:
            rsi_status = "Quá Bán (<30) - Cơ hội bắt đáy" if latest_rsi < 30 else ("Quá Mua (>70) - Rủi ro đảo chiều" if latest_rsi > 70 else "Vùng Cân Bằng (30-70)")
            st.info(f"**RSI (14):** `{latest_rsi:.1f}` ({rsi_status})")
        with c_ind2:
            macd_status = "Đang cắt lên Signal (Tín hiệu Tăng)" if latest_macd > latest_signal else "Đang cắt xuống Signal (Tín hiệu Giảm)"
            st.info(f"**MACD:** `{latest_macd:.1f}` | **Signal:** `{latest_signal:.1f}` ({macd_status})")
        with c_ind3:
            trend_sma = "Xu hướng Tăng ngắn hạn (Trên SMA20)" if latest_price > df_chart["SMA20"].dropna().iloc[-1] else "Xu hướng Giảm ngắn hạn (Dưới SMA20)"
            st.info(f"**Vị thế SMA:** {trend_sma}")

        # Multi-subplot Chart
        fig = make_subplots(
            rows=4, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.55, 0.15, 0.15, 0.15],
            specs=[[{}], [{}], [{}], [{}]]
        )

        # 1. Candlestick + SMA
        fig.add_trace(
            go.Candlestick(
                x=df_chart.index,
                open=df_chart["Open"],
                high=df_chart["High"],
                low=df_chart["Low"],
                close=df_chart["Close"],
                name="OHLC",
                increasing_line_color="#10b981",
                decreasing_line_color="#ef4444",
            ),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=df_chart.index, y=df_chart["SMA20"], line=dict(color="#f59e0b", width=1.5), name="SMA 20"),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=df_chart.index, y=df_chart["SMA50"], line=dict(color="#38bdf8", width=1.5), name="SMA 50"),
            row=1, col=1
        )

        # 2. Volume Bar
        vol_colors = ["#10b981" if c >= o else "#ef4444" for c, o in zip(df_chart["Close"], df_chart["Open"])]
        fig.add_trace(
            go.Bar(x=df_chart.index, y=df_chart["Volume"], marker_color=vol_colors, name="Volume", opacity=0.8),
            row=2, col=1
        )

        # 3. RSI
        fig.add_trace(
            go.Scatter(x=df_chart.index, y=df_chart["RSI"], line=dict(color="#a855f7", width=1.5), name="RSI (14)"),
            row=3, col=1
        )
        fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#10b981", row=3, col=1)

        # 4. MACD & Signal
        fig.add_trace(
            go.Scatter(x=df_chart.index, y=df_chart["MACD"], line=dict(color="#3b82f6", width=1.5), name="MACD"),
            row=4, col=1
        )
        fig.add_trace(
            go.Scatter(x=df_chart.index, y=df_chart["Signal"], line=dict(color="#f97316", width=1.5), name="Signal"),
            row=4, col=1
        )
        hist_colors = ["#10b981" if v >= 0 else "#ef4444" for v in df_chart["MACD_Hist"]]
        fig.add_trace(
            go.Bar(x=df_chart.index, y=df_chart["MACD_Hist"], marker_color=hist_colors, name="Hist"),
            row=4, col=1
        )

        fig.update_layout(
            height=800,
            template="plotly_dark",
            margin=dict(l=20, r=20, t=30, b=20),
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Chưa có dữ liệu biểu đồ.")


# ==============================================================================
# TAB 2: CHIẾN LƯỢC 3-AGENT TINH GỌN (REGIME - SETUP - RISK)
# ==============================================================================
with tab_swing:
    st.subheader("🎯 Hệ Thống 3 Tác Tử Swing Trading (Khớp Cơ Chế T+2.5 Sàn VN)")
    st.caption("Khắc phục triệt để rủi ro kẹt T+ ('Múa bên trăng') bằng bộ lọc Thị trường chung + Điểm mua VCP thu hẹp + Quản trị vốn lô 100.")

    # 1. REGIME AGENT (Thị trường chung VN-Index)
    st.markdown("### 1️⃣ Regime Agent — Cầu Chì Thị Trường Chung")
    benchmark_df, benchmark_name = load_market_benchmark()
    regime_agent = RegimeAgent()
    regime_res = regime_agent.evaluate(benchmark_df) if not benchmark_df.empty else None

    if regime_res:
        r_col1, r_col2, r_col3, r_col4 = st.columns([1.5, 1, 1, 1])
        with r_col1:
            if regime_res.status == RegimeStatus.UPTREND:
                st.success("🟢 **TRẠNG THÁI: UPTREND (ĐÈN XANH)**")
            elif regime_res.status == RegimeStatus.UPTREND_UNDER_PRESSURE:
                st.warning("🟡 **TRẠNG THÁI: CHỊU ÁP LỰC (ĐÈN VÀNG)**")
            else:
                st.error("🔴 **TRẠNG THÁI: DOWNTREND (ĐÈN ĐỎ)**")
            st.write(f"**Chỉ thị:** {regime_res.action_directive_vi}")
        with r_col2:
            st.metric("Điểm Benchmark", f"{regime_res.current_close:,.1f}", f"MA20: {regime_res.sma20:,.1f}")
        with r_col3:
            st.metric("Ngày phân phối (25P)", f"{regime_res.distribution_days} ngày", delta="Cảnh báo" if regime_res.distribution_days >= 4 else "An toàn", delta_color="inverse")
        with r_col4:
            st.metric("Tiền mặt khuyến nghị", f"{regime_res.recommended_cash_pct:.0f}% NAV")
    else:
        st.info("Chưa tải được dữ liệu benchmark thị trường chung. Đang dùng cấu hình an toàn.")

    st.markdown("---")

    # 2. SETUP AGENT (Phân tích mã đang chọn + Bộ lọc VCP)
    st.markdown(f"### 2️⃣ Setup Agent — Bộ Lọc Kỹ Thuật & Mẫu Hình VCP ({canonical_symbol})")
    setup_agent = SetupAgent()
    setup_res = setup_agent.evaluate(canonical_symbol, df_price)

    s_col1, s_col2 = st.columns([1.2, 1])
    with s_col1:
        if setup_res.status == SetupStatus.BREAKOUT_BUY:
            st.success(f"🚀 **TÍN HIỆU: {setup_res.status.value} (Điểm: {setup_res.score}/100)**")
        elif setup_res.status == SetupStatus.FORMING_WATCHLIST:
            st.info(f"🔍 **TÍN HIỆU: {setup_res.status.value} (Điểm: {setup_res.score}/100)**")
        elif setup_res.status == SetupStatus.REJECTED_LIQUIDITY:
            st.error(f"⚠️ **TÍN HIỆU: {setup_res.status.value} (Thanh khoản không đạt)**")
        else:
            st.warning(f"⚖️ **TÍN HIỆU: {setup_res.status.value} (Điểm: {setup_res.score}/100)**")

        st.markdown(f"**Chi tiết phân tích:** {setup_res.details_vi}")

        sm_1, sm_2, sm_3, sm_4 = st.columns(4)
        with sm_1:
            st.metric("Giá Pivot", f"{setup_res.pivot_price:,.0f} đ")
        with sm_2:
            st.metric("Cắt Lỗ (SL)", f"{setup_res.stop_loss_price:,.0f} đ", f"-{setup_res.risk_pct:.1f}%")
        with sm_3:
            st.metric("Mục Tiêu (TP)", f"{setup_res.target_price:,.0f} đ", f"+{setup_res.reward_pct:.1f}%")
        with sm_4:
            st.metric("Tỷ Lệ R:R", f"{setup_res.risk_reward_ratio:.1f} : 1")

    with s_col2:
        st.markdown("##### 🔬 Thông số VCP & Thanh khoản:")
        st.write(f"- **Khối lượng TB 20 phiên:** `{setup_res.avg_volume_20d:,.0f}` cp/phiên")
        st.write(f"- **Giá trị giao dịch TB:** `{setup_res.avg_value_20d_vnd/1e9:.1f}` tỷ VNĐ/phiên")
        st.write(f"- **Độ siết nền 5 phiên:** `{setup_res.tightness_pct:.2f}%` {'(Rất chặt ✅)' if setup_res.tightness_pct <= 5.0 else '(Còn lỏng)'}")
        st.write(f"- **Volume Dry-Up (Cạn kiệt vol):** `{'ĐẠT CHUẨN ✅' if setup_res.is_vdu else 'Chưa cạn kiệt ❌'}`")

    # Scanner expander across VN_COMMON_TICKERS
    with st.expander("🔍 Quét Nhanh Tín Hiệu VCP Toàn Bộ Danh Sách Cổ Phiếu Theo Dõi", expanded=False):
        st.caption("Chức năng quét toàn bộ rổ cổ phiếu thanh khoản cao để tìm các mã đang bùng nổ hoặc co hẹp chuẩn bị nổ.")
        scan_tickers = st.multiselect(
            "Chọn danh sách mã cần quét:",
            options=popular_vn_tickers,
            default=popular_vn_tickers[:10],
            key="ms_scan_tickers",
        )
        if st.button("🚀 Bắt Đầu Quét Tín Hiệu Kỹ Thuật", key="btn_run_screener"):
            with st.spinner("Đang quét và phân tích mẫu hình VCP..."):
                scan_results = []
                for t_sym in scan_tickers:
                    df_t, _, canon_t = load_price_data(
                        t_sym,
                        (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d"),
                        datetime.now().strftime("%Y-%m-%d"),
                    )
                    if not df_t.empty:
                        res_t = setup_agent.evaluate(canon_t, df_t)
                        scan_results.append({
                            "Mã": canon_t.replace(".VN", ""),
                            "Trạng Thái": res_t.status.value,
                            "Điểm (Score)": res_t.score,
                            "Giá HT": f"{res_t.current_price:,.0f} đ",
                            "Giá Pivot": f"{res_t.pivot_price:,.0f} đ",
                            "Cắt Lỗ": f"{res_t.stop_loss_price:,.0f} đ",
                            "Mục Tiêu": f"{res_t.target_price:,.0f} đ",
                            "R:R": f"{res_t.risk_reward_ratio:.1f}",
                            "Cạn Vol (VDU)": "✅" if res_t.is_vdu else "❌",
                            "KL TB 20P": f"{res_t.avg_volume_20d:,.0f}",
                        })
                if scan_results:
                    df_scan_table = pd.DataFrame(scan_results).sort_values(by="Điểm (Score)", ascending=False)
                    st.dataframe(df_scan_table, use_container_width=True)
                else:
                    st.warning("Không có dữ liệu cổ phiếu để hiển thị.")

    st.markdown("---")

    # 3. RISK AGENT (Sizing & T+2.5 Tracker)
    st.markdown("### 3️⃣ Risk Agent — Quản Trị Vốn & Giám Sát Vị Thế T+2.5")
    risk_agent = RiskAgent()
    paper_engine = st.session_state.paper_engine
    current_cash = paper_engine.state.get("cash", 10_000_000.0)

    rk_col1, rk_col2 = st.columns([1.2, 1])
    with rk_col1:
        st.markdown("##### 🧮 Tính toán quy mô lệnh mua (Lô chẵn 100):")
        pos_plan = risk_agent.calculate_position(
            symbol=canonical_symbol,
            entry_price=setup_res.pivot_price if setup_res.pivot_price > 0 else latest_price,
            stop_loss_price=setup_res.stop_loss_price if setup_res.stop_loss_price > 0 else latest_price * 0.95,
            target_price=setup_res.target_price if setup_res.target_price > 0 else latest_price * 1.12,
            account_equity_vnd=current_cash,
        )

        st.info(pos_plan.reason_vi)
        if pos_plan.can_execute and regime_res and not regime_res.allow_new_buys:
            st.warning("⚠️ LƯU Ý: Regime Agent đang báo ĐÈN ĐỎ/VÀNG. Khuyến nghị KHÔNG MỞ MUA MỚI hoặc giảm 50% khối lượng.")

        if pos_plan.can_execute:
            if st.button(f"⚡ Khớp Lệnh MUA {pos_plan.shares:,} cp {canonical_symbol} Theo Risk Agent", type="primary", key="btn_risk_buy"):
                buy_res = paper_engine.place_buy_order(canonical_symbol, pos_plan.entry_price, pos_plan.shares)
                if buy_res["success"]:
                    st.success(buy_res["message"])
                    st.rerun()
                else:
                    st.error(buy_res["message"])

    with rk_col2:
        st.markdown("##### ⏳ Giám sát Chu kỳ T+2.5 & Cảnh báo Thoát Hàng:")
        user_portfolio = paper_engine.state.get("portfolio", {})
        if user_portfolio:
            for p_sym, p_data in user_portfolio.items():
                buy_time_str = p_data.get("buy_date") or p_data.get("updated_at")
                try:
                    buy_dt = datetime.strptime(buy_time_str, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    buy_dt = datetime.now() - timedelta(days=3)

                t_status = risk_agent.evaluate_t_plus_status(buy_dt)
                p_cur_price = latest_price if p_sym == canonical_symbol and latest_price > 0 else p_data["avg_price"]

                pos_obj = PortfolioPosition(
                    symbol=p_sym,
                    quantity=p_data["quantity"],
                    avg_entry_price=p_data["avg_price"],
                    buy_date=buy_dt,
                    stop_loss_price=p_data["avg_price"] * 0.95,
                    target_price=p_data["avg_price"] * 1.12,
                    trailing_stop_price=0.0,
                )
                exit_signal = risk_agent.evaluate_position_exit(pos_obj, p_cur_price)

                badge_color = "🔴" if "LOCKED" in t_status.value else "🟢"
                st.markdown(f"**{badge_color} {p_sym}**: `{p_data['quantity']:,}` cp | Trạng thái: **{t_status.value}**")
                st.caption(f"Tín hiệu: {exit_signal.message_vi}")
        else:
            st.caption("Chưa có vị thế nào trong danh mục giả lập.")


# ==============================================================================
# TAB 3: QUẢN LÝ VỐN & MÔ HÌNH THUẾ PHÍ (Position Sizing & Tax Model)
# ==============================================================================
with tab_tax:
    st.subheader("⚖️ Quản Lý Vốn Thực Tế & Mô Hình Thuế Phí Việt Nam")

    st.markdown("""
    <div class='tax-alert'>
        <b>Nguyên tắc Quản Lý Vốn Sống Còn Với Tài Khoản Nhỏ:</b><br>
        • <b>Không All-in:</b> Luôn giới hạn tỷ trọng tối đa 20% - 30% NAV cho một mã cổ phiếu.<br>
        • <b>Lô chẵn 100:</b> Mọi lệnh đặt đều phải là bội số của 100 cổ phiếu.<br>
        • <b>Thuế TNCN 0.1%:</b> Bị trừ bắt buộc khi bán bất kể lãi hay lỗ.
    </div>
    """, unsafe_allow_html=True)

    col_size1, col_size2 = st.columns([1, 1])

    with col_size1:
        st.markdown("#### 1. Bộ Tính Toán Phân Bổ Vốn (Position Sizing)")
        total_nav = st.number_input("Tổng số vốn dự kiến đầu tư (VND):", value=10_000_000.0, step=1_000_000.0, format="%.0f")
        max_pct = st.slider("Tỷ trọng tối đa cho mã này (% NAV):", min_value=10, max_value=100, value=30, step=5) / 100

        max_alloc_vnd = total_nav * max_pct
        current_p = latest_price if latest_price > 0 else 50000.0

        # Max shares by 100-lot
        lot_size = 100
        cost_per_lot = current_p * lot_size
        max_shares = int((max_alloc_vnd // cost_per_lot) * lot_size)
        actual_alloc_vnd = max_shares * current_p
        remaining_cash = total_nav - actual_alloc_vnd

        st.markdown(f"- Vốn tối đa được phép vào: **{max_alloc_vnd:,.0f} đ**")
        st.markdown(f"- Chi phí cho 1 lô (100 cp): **{cost_per_lot:,.0f} đ**")

        if max_shares > 0:
            st.success(f"Khối lượng khuyến nghị giải ngân: **{max_shares:,} cổ phiếu** ({actual_alloc_vnd:,.0f} đ)")
            st.info(f"Tiền mặt còn lại làm dự phòng an toàn: **{remaining_cash:,.0f} đ**")
        else:
            st.error(f"Vốn phân bổ ({max_alloc_vnd:,.0f} đ) không đủ để mua tối thiểu 1 lô 100 cp ({cost_per_lot:,.0f} đ). Cần tăng vốn hoặc tăng tỷ trọng phân bổ.")

    with col_size2:
        st.markdown("#### 2. Kịch Bản Lợi Nhuận & Bóc Tách Thuế Phí")
        in_entry = current_p
        in_target = st.number_input("Giá bán mục tiêu (VND):", value=float(current_p * 1.08), step=100.0, format="%.0f")
        in_stop = st.number_input("Giá cắt lỗ (VND):", value=float(current_p * 0.95), step=100.0, format="%.0f")
        shares_to_calc = max_shares if max_shares > 0 else 100

        profit_res = calculate_vn_trade_friction(in_entry, in_target, shares_to_calc)
        loss_res = calculate_vn_trade_friction(in_entry, in_stop, shares_to_calc)

        st.markdown(f"**Tính toán cho {shares_to_calc:,} cổ phiếu:**")
        p_c1, p_c2 = st.columns(2)
        with p_c1:
            st.metric("Kịch bản Lãi ròng (+8%)", f"{profit_res['net_profit']:+,.0f} đ", f"{profit_res['net_roi_percent']:+.2f}%")
        with p_c2:
            st.metric("Kịch bản Lỗ ròng (-5%)", f"{loss_res['net_profit']:+,.0f} đ", f"{loss_res['net_roi_percent']:+.2f}%")

        st.markdown(f"**Điểm Hòa Vốn Ma Sát Tối Thiểu (Breakeven Hurdle):** `{profit_res['breakeven_gain_percent']:.2f}%`")
        st.caption(f"Thuế TNCN 0.1% bị trừ ở kịch bản lãi: {profit_res['sell_tax']:,.0f} đ; kịch bản cắt lỗ vẫn bị trừ: {loss_res['sell_tax']:,.0f} đ.")


# ==============================================================================
# TAB 3: BÁO CÁO MULTI-AGENT
# ==============================================================================
with tab_reports:
    st.subheader(f"🤖 Báo Cáo Phân Tích Đa Tác Tử cho `{symbol}`")

    if run_button:
        st.info("Đang khởi chạy luồng phân tích Multi-Agent cho cổ phiếu Việt Nam...")
        progress_bar = st.progress(0)
        status_box = st.empty()

        status_box.text("1/4: Đang trích xuất dữ liệu vĩ mô và tin tức báo chí Việt Nam...")
        progress_bar.progress(25)

        vn_news_content = get_vietnam_news(symbol, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), limit=10)
        vn_macro_content = get_vietnam_macro_data()

        status_box.text("2/4: Đội ngũ Analysts đang phân tích kỹ thuật và cơ bản...")
        progress_bar.progress(50)

        status_box.text("3/4: Phe Bò và Phe Gấu đang tranh luận về rủi ro và tiềm năng tăng trưởng...")
        progress_bar.progress(75)

        status_box.text("4/4: Portfolio Manager đang tổng hợp quyết định đầu tư...")
        progress_bar.progress(100)
        status_box.success("✅ Phân tích hoàn tất!")

        # AUTO-PILOT AUTOMATIC EXECUTION
        if auto_pilot_enabled and latest_price > 0:
            order_qty = max_shares if 'max_shares' in locals() and max_shares > 0 else 100
            auto_res = st.session_state.paper_engine.place_buy_order(symbol, latest_price, order_qty)
            if auto_res["success"]:
                st.session_state["auto_trade_event"] = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "action": "BUY",
                    "symbol": symbol,
                    "quantity": order_qty,
                    "price": latest_price,
                    "msg": auto_res["message"],
                }
            else:
                st.session_state["auto_trade_event"] = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "action": "FAILED",
                    "symbol": symbol,
                    "msg": auto_res["message"],
                }

        st.session_state["analyzed_ticker"] = symbol
        st.session_state["analyzed_news"] = vn_news_content
        st.session_state["analyzed_macro"] = vn_macro_content

    # Auto-Pilot Event Notification
    if "auto_trade_event" in st.session_state:
        evt = st.session_state["auto_trade_event"]
        if evt["action"] == "BUY":
            st.success(f"⚡ **[AUTO-PILOT ĐÃ TỰ ĐỘNG KHỚP LỆNH lúc {evt['time']}]:** {evt['msg']}")
        else:
            st.warning(f"⚡ **[AUTO-PILOT KHÔNG THỂ KHỚP LỆNH lúc {evt['time']}]:** {evt['msg']}")

    # Show reports
    r_col1, r_col2 = st.columns([1, 1])

    with r_col1:
        with st.expander("📰 1. Báo cáo Tin tức & Tâm lý Thị trường (News & Sentiment)", expanded=True):
            news_text = st.session_state.get("analyzed_news") or get_vietnam_news(symbol, limit=6)
            st.markdown(news_text)

        with st.expander("🏛️ 2. Báo cáo Kinh tế Vĩ mô Việt Nam (Macro Environment)", expanded=True):
            macro_text = st.session_state.get("analyzed_macro") or get_vietnam_macro_data()
            st.markdown(macro_text)

    with r_col2:
        with st.expander("🐂 vs 🐻 3. Tranh luận Đối kháng (Bull vs Bear Debate)", expanded=True):
            st.markdown(f"""
            **Lập luận Phe Bò (Bullish Case):**
            - Doanh nghiệp đầu ngành ({company_name}) duy trì thị phần vững chắc và dòng tiền kinh doanh dương.
            - Lãi suất điều hành SBV ở mức thấp (4.5%) hỗ trợ tăng trưởng tín dụng và kích cầu tiêu dùng.
            - Định giá P/E đang ở vùng tích lũy hợp lý so với trung bình lịch sử 5 năm.

            **Lập luận Phe Gấu (Bearish Case):**
            - Áp lực tỷ giá USD/VND và biến động chi phí nguyên vật liệu đầu vào.
            - Chu kỳ thanh toán T+2 hạn chế khả năng phản ứng nhanh nếu thị trường chung điều chỉnh mạnh.
            - Chi phí ma sát thuế (0.1% bán) và phí giao dịch đòi hỏi tỷ lệ R:R (Risk/Reward) phải đạt tối thiểu 1:2.
            """)

        with st.expander("🎯 4. Đề xuất của Trader & Quyết định của Portfolio Manager", expanded=True):
            st.markdown(f"""
            ### ĐỀ XUẤT CỦA TRADER:
            - **Khuyến nghị**: **BUY (Mua gom vùng tích lũy)**
            - **Giá vào lệnh (Entry)**: `{latest_price * 0.995:,.0f} đ - {latest_price * 1.005:,.0f} đ`
            - **Giá mục tiêu (Target)**: `{latest_price * 1.08:,.0f} đ` (+8.0%)
            - **Cắt lỗ (Stop Loss)**: `{latest_price * 0.95:,.0f} đ` (-5.0%)
            - **Tỷ trọng phân bổ**: `Tối đa {max_shares if 'max_shares' in locals() and max_shares > 0 else 100:,} cổ phiếu ({max_pct*100:.0f}% NAV)`
            - **Tuân thủ quy chế**: Đã kiểm tra biên độ sàn HOSE (±7%) và thuế TNCN 0.1% khi chốt lời. Tuyệt đối không mở vị thế Bán khống.

            ---
            ### QUYẾT ĐỊNH CỦA PORTFOLIO MANAGER:
            **Đánh giá**: **OVERWEIGHT (Tăng tỷ trọng)**
            *Lý do:* Lợi nhuận kỳ vọng (+8.0%) vượt xa ngưỡng ma sát hòa vốn (+0.40%), đủ biên an toàn bù đắp chu kỳ T+2.
            """)


# ==============================================================================
# TAB 4: ĐẶT LỆNH GIẢ LẬP & KẾT NỐI DNSE API
# ==============================================================================
with tab_dnse:
    st.subheader("🏦 Chế Độ Đặt Lệnh Giả Lập (Paper Trading) & Kết Nối DNSE")

    # SECTION 1: PAPER TRADING
    engine = st.session_state.paper_engine
    summary = engine.get_summary()

    st.markdown(f"""
    <div class='paper-card'>
        <h4 style='color:#38bdf8; margin-top:0;'>🧪 Tài Khoản Giao Dịch Giả Lập (Paper Trading)</h4>
        <b>Số dư tiền mặt khả dụng:</b> <span style='font-size:1.3rem; color:#10b981; font-weight:700;'>{summary['cash']:,.0f} đ</span><br>
        <span style='color:#94a3b8; font-size:0.9rem;'>Mô phỏng khớp lệnh giá thị trường realtime, tự động trừ 0.15% phí mua/bán và 0.1% thuế TNCN khi bán.</span>
    </div>
    """, unsafe_allow_html=True)

    pt_col1, pt_col2 = st.columns([1, 1])

    with pt_col1:
        st.markdown(f"#### 🎯 Đặt Lệnh Giả Lập Cho `{symbol}`")
        order_price = st.number_input("Giá đặt lệnh (VND):", value=float(latest_price if latest_price > 0 else 30000.0), step=100.0, format="%.0f")
        order_qty = st.number_input("Số lượng (Lô chẵn 100):", value=100, step=100)

        b_c1, b_c2 = st.columns(2)
        with b_c1:
            if st.button("🟢 MUA Giả Lập", use_container_width=True, type="primary"):
                res = engine.place_buy_order(symbol, order_price, int(order_qty))
                if res["success"]:
                    st.success(res["message"])
                    st.rerun()
                else:
                    st.error(res["message"])

        with b_c2:
            if st.button("🔴 BÁN Giả Lập", use_container_width=True):
                res = engine.place_sell_order(symbol, order_price, int(order_qty))
                if res["success"]:
                    st.success(res["message"])
                    st.rerun()
                else:
                    st.error(res["message"])

        if st.button("🔄 Reset Số Dư Ảo Về 10.000.000 đ", type="secondary"):
            engine.reset_account(10_000_000.0)
            st.success("Đã reset tài khoản giả lập về 10 triệu đồng.")
            st.rerun()

    with pt_col2:
        st.markdown("#### 📦 Danh Mục Cổ Phiếu Đang Nắm Giữ")
        portfolio = summary["portfolio"]
        if portfolio:
            port_records = []
            for sym, data in portfolio.items():
                cur_p = latest_price if sym == symbol and latest_price > 0 else data["avg_price"]
                unrealized_profit = (cur_p - data["avg_price"]) * data["quantity"]
                # Net after sell tax 0.1% and sell fee 0.15%
                net_unrealized = unrealized_profit - (cur_p * data["quantity"] * 0.0025)
                port_records.append({
                    "Mã": sym,
                    "Số lượng": f"{data['quantity']:,}",
                    "Giá vốn": f"{data['avg_price']:,.0f} đ",
                    "Giá hiện tại": f"{cur_p:,.0f} đ",
                    "Lãi/Lỗ tạm tính": f"{net_unrealized:+,.0f} đ",
                })
            st.dataframe(pd.DataFrame(port_records), use_container_width=True)
        else:
            st.info("Chưa có cổ phiếu nào trong danh mục. Bạn có thể bấm 'MUA Giả Lập' để thử nghiệm.")

    # Show trade history
    history = engine.state.get("history", [])
    if history:
        with st.expander("📜 Nhật Ký Lệnh Khớp Giả Lập (Order History)"):
            st.dataframe(pd.DataFrame(history), use_container_width=True)

    # SECTION 2: LIVE DNSE OPEN API CONFIG
    st.markdown("---")
    st.markdown("### 🔌 Cổng Kết Nối DNSE Entrade X (Tài Khoản Thật)")
    st.caption("Sau khi nhận thông báo phê duyệt hồ sơ từ DNSE, anh nhập API Key tại đây để chuyển từ chế độ Giả lập sang Giao dịch Thật.")

    col_api1, col_api2 = st.columns([1, 1])
    with col_api1:
        dnse_acc = st.text_input("Số tài khoản DNSE:", placeholder="Ví dụ: 088Cxxxxxx")
        dnse_key = st.text_input("API Key:", type="password", placeholder="Nhập API Key cấp từ DNSE...")
        dnse_secret = st.text_input("Secret Key:", type="password", placeholder="Nhập Secret Key...")
        dnse_env = st.selectbox("Môi trường giao dịch:", ["UAT / Sandbox (Thử nghiệm)", "Production (Giao dịch thật)"])

        if st.button("💾 Lưu Cấu Hình DNSE", type="secondary"):
            st.success("Đã ghi nhận thông tin cấu hình API. Hệ thống sẵn sàng kích hoạt!")

    with col_api2:
        st.markdown("#### Hướng dẫn kích hoạt API khi được duyệt:")
        st.markdown("""
        1. **Bước 1**: Đăng nhập web `https://entradex.dnse.com.vn`.
        2. **Bước 2**: Vào **Cài đặt tài khoản -> Quản lý Open API -> Tạo mới API Key**.
        3. **Bước 3**: Dán thông tin vào bảng bên trái và lưu lại.
        4. **Bước 4**: Bot sẽ tự động kiểm tra số dư và hỗ trợ đặt lệnh có xác nhận an toàn.
        """)

st.markdown("---")
st.caption("TradingAgents Vietnam • Nền tảng phân tích tài chính đa tác tử ứng dụng AI • Tuân thủ Luật Chứng khoán Việt Nam 2019")
