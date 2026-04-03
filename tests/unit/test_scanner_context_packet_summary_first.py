import json

import agent_os.backend.services.scanner_context as scanner_mod
from agent_os.backend.services.langgraph_engine import LangGraphEngine


class _StubTool:
    def __init__(self, payload: str):
        self.payload = payload

    def invoke(self, _args):
        return self.payload


def _patch_ground_truth_tools(monkeypatch):
    monkeypatch.setattr(
        scanner_mod,
        "get_gold_price",
        _StubTool(
            """
| Asset | Symbol | Current Price | Change | Change % |
|---|---|---:|---:|---:|
| Gold | GC=F | $2,100.00 | +10.00 | +0.48% |
"""
        ),
    )
    monkeypatch.setattr(
        scanner_mod,
        "get_oil_prices",
        _StubTool(
            """
| Asset | Symbol | Current Price | Change | Change % |
|---|---|---:|---:|---:|
| WTI Crude | CL=F | $82.10 | +1.10 | +1.36% |
| Brent Crude | BZ=F | $85.40 | +0.80 | +0.95% |
"""
        ),
    )
    monkeypatch.setattr(
        scanner_mod,
        "get_bitcoin_price",
        _StubTool(
            """
| Asset | Symbol | Current Price | Change | Change % |
|---|---|---:|---:|---:|
| Bitcoin | BTC-USD | $66,000.00 | -500.00 | -0.75% |
"""
        ),
    )
    monkeypatch.setattr(
        scanner_mod,
        "get_eur_usd_rate",
        _StubTool(
            """
| Asset | Symbol | Current Price | Change | Change % |
|---|---|---:|---:|---:|
| EUR/USD | EURUSD=X | $1.10 | +0.00 | +0.10% |
"""
        ),
    )
    monkeypatch.setattr(
        scanner_mod,
        "get_jpy_usd_rate",
        _StubTool(
            """
| Asset | Symbol | Current Price | Change | Change % |
|---|---|---:|---:|---:|
| JPY/USD | JPYUSD=X | $0.01 | -0.00 | -0.20% |
"""
        ),
    )
    monkeypatch.setattr(
        scanner_mod,
        "get_cny_usd_rate",
        _StubTool(
            """
| Asset | Symbol | Current Price | Change | Change % |
|---|---|---:|---:|---:|
| CNY/USD | CNYUSD=X | $0.14 | +0.00 | +0.05% |
"""
        ),
    )
    monkeypatch.setattr(
        scanner_mod,
        "get_earnings_calendar",
        _StubTool(
            """
| Symbol | Company | Date | EPS Estimate | EPS Prior | Revenue Estimate |
|--------|---------|------|--------------|-----------|-----------------|
| MSFT | Microsoft | 2026-04-10 | $2.70 | $2.45 | $60.00B |
| AAPL | Apple | 2026-04-12 | $2.10 | $1.88 | $110.00B |
| TSLA | Tesla | 2026-04-13 | $0.90 | $0.73 | $26.00B |
| AMZN | Amazon | 2026-04-16 | $1.30 | $1.00 | $170.00B |
"""
        ),
    )
    monkeypatch.setattr(
        scanner_mod,
        "get_economic_calendar",
        _StubTool(
            """
| Event | Country | Impact | Date |
|-------|---------|--------|------|
| CPI | US | High | 2026-04-09 |
| Retail Sales | US | Medium | 2026-04-11 |
| FOMC Minutes | US | High | 2026-04-15 |
| Housing Starts | US | Low | 2026-04-16 |
"""
        ),
    )


def _base_macro_summary() -> str:
    payload = {
        "stocks_to_investigate": [
            {
                "ticker": "MSFT",
                "sector": "Technology / Software",
                "rationale": "Cloud AI demand and margin durability.",
                "thesis_angle": "quality-growth",
                "conviction": "high",
                "key_catalysts": ["Azure growth re-acceleration", "Copilot monetization"],
                "risks": ["Enterprise spending slowdown"],
            },
            {
                "ticker": "AAPL",
                "sector": "Technology / Hardware",
                "rationale": "Services resilience.",
            },
            {
                "ticker": "AMZN",
                "sector": "Consumer / Cloud",
                "rationale": "Operating leverage from AWS and ads.",
            },
        ],
        "key_themes": [
            {
                "theme": "AI Infrastructure",
                "description": "Large-cap capex remains elevated.",
                "conviction": "high",
            },
            {
                "theme": "Quality Rotation",
                "description": "Cash-generative software leadership.",
                "conviction": "medium",
            },
        ],
        "risk_factors": [
            "Rates remain restrictive for longer.",
            "AI capex payback uncertainty.",
        ],
    }
    return json.dumps(payload)


def test_scanner_context_packet_prefers_summaries_over_raw_reports(monkeypatch):
    _patch_ground_truth_tools(monkeypatch)

    raw_marker = "RAW_REPORT_SHOULD_NOT_APPEAR"
    scan_state = {
        "scan_date": "2026-04-02",
        "macro_scan_summary": _base_macro_summary(),
        "smart_money_summary": "MSFT dark-pool accumulation increased 14% WoW.\nTSLA put activity rose.",
        "factor_alignment_summary": "MSFT factor alignment: Quality +0.8, Momentum +0.5.",
        "drift_opportunities_summary": "MSFT positive drift persisted for 8 sessions.",
        "sector_summary": "Technology leadership remains intact; software breadth improved.",
        "geopolitical_summary": "Trade controls remain a watchpoint for semis.",
        "market_movers_summary": "Large-cap software outperformed cyclicals this week.",
        "industry_deep_dive_summary": "Enterprise software budgets stabilized in Q2 checks.",
        # Raw reports should not leak into the packet.
        "smart_money_report": raw_marker,
        "factor_alignment_report": raw_marker,
        "drift_opportunities_report": raw_marker,
        "geopolitical_report": raw_marker,
        "sector_performance_report": raw_marker,
    }

    packet = LangGraphEngine._build_scanner_context_packet(scan_state, "MSFT")

    assert raw_marker not in packet
    assert "## 1) Selection Context" in packet
    assert "## 2) Ground Truth" in packet
    assert "## 3) Ticker-Relevant Scanner Signals" in packet
    assert "## 4) Sector Context" in packet
    assert "## 5) Macro Themes" in packet
    assert "## 6) Risk Factors" in packet
    assert "MSFT dark-pool accumulation increased 14% WoW." in packet
    assert "MSFT factor alignment: Quality +0.8, Momentum +0.5." in packet
    assert "MSFT positive drift persisted for 8 sessions." in packet
    assert "MSFT 2026-04-10 EPS $2.70 Rev $60.00B" in packet


def test_scanner_context_packet_is_bounded_vs_raw_payload_and_audit_scale(monkeypatch):
    _patch_ground_truth_tools(monkeypatch)

    # Reference from model_context audit dated 2026-04-02:
    # scanner context was measured at 73,444 chars in run 01KN7AX94HC86NENW9QCSPP2KB.
    benchmark_scanner_context_chars = 73_444

    large_raw_block = ("RAW_PAYLOAD " * 5000).strip()
    scan_state = {
        "scan_date": "2026-04-02",
        "macro_scan_summary": _base_macro_summary(),
        "smart_money_summary": "MSFT institutional buy-side flow remains positive.",
        "factor_alignment_summary": "MSFT quality factor leadership persists.",
        "drift_opportunities_summary": "MSFT drift remains positive short-term.",
        "sector_summary": "Technology/software leadership remains positive.",
        "geopolitical_summary": "Macro policy uncertainty persists.",
        "market_movers_summary": "Software outperformed market beta.",
        "industry_deep_dive_summary": "Enterprise software spending remained resilient.",
        "smart_money_report": large_raw_block,
        "factor_alignment_report": large_raw_block,
        "drift_opportunities_report": large_raw_block,
        "geopolitical_report": large_raw_block,
        "sector_performance_report": large_raw_block,
    }

    packet = LangGraphEngine._build_scanner_context_packet(scan_state, "MSFT")

    raw_payload_chars = (
        len(scan_state["smart_money_report"])
        + len(scan_state["factor_alignment_report"])
        + len(scan_state["drift_opportunities_report"])
        + len(scan_state["geopolitical_report"])
        + len(scan_state["sector_performance_report"])
    )
    assert len(packet) < raw_payload_chars * 0.15
    assert len(packet) < benchmark_scanner_context_chars * 0.25
    assert packet.count("RAW_PAYLOAD") == 0
