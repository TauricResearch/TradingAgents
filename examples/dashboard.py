"""
Carry Trade Dashboard
=====================
Web-based monitoring dashboard for carry trade portfolio.

Features:
- Real-time market data visualization
- Portfolio positions and P&L
- Carry trade opportunities
- Interest rate comparison
- FX rate tracking
- Alert system

Usage:
    python examples/dashboard.py
    python examples/dashboard.py --port 8080
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradingagents.dataflows.providers.interest_rates import GlobalInterestRatesProvider
from tradingagents.dataflows.providers.fx_multi_currency import MultiCurrencyFXProvider

# Tick-panel helpers (Step 5) — no hard dep, degrades gracefully
try:
    from tradingagents.dashboard import (
        add_rule,
        detect_abnormal,
        get_rotation_matrix,
        get_watchlist,
        list_alerts,
        list_rules,
        sse_format,
    )

    _HAS_TICK_PANEL = True
except Exception:  # noqa: BLE001
    _HAS_TICK_PANEL = False

app = Flask(__name__)

# Initialize providers
rates_provider = GlobalInterestRatesProvider()
fx_provider = MultiCurrencyFXProvider()


def get_market_data():
    """Fetch current market data"""
    rates = rates_provider.get_all_rates()
    
    fx_pairs = [
        "USD_BRL", "USD_TRY", "USD_MXN", "USD_INR", 
        "USD_ZAR", "USD_ARS", "USD_CLP", "USD_PLN",
        "USD_COP", "USD_IDR", "USD_THB", "USD_PHP",
    ]
    fx_rates = {}
    
    for pair in fx_pairs:
        base, quote = pair.split("_")
        rate = fx_provider.get_rate(base, quote)
        if rate:
            fx_rates[pair] = rate.rate
    
    return {
        "rates": rates,
        "fx_rates": fx_rates,
        "timestamp": datetime.now().isoformat(),
    }


def calculate_carry_trades(market_data):
    """Calculate carry trade opportunities"""
    rates = market_data["rates"]
    fx_rates = market_data["fx_rates"]
    
    us_rate = rates.get("US")
    if not us_rate:
        return []
    
    carry_trades = []
    
    # All currencies we track
    currencies = ["BR", "MX", "IN", "ZA", "CL", "TR", "PL", "CO", "ID", "TH", "PH"]
    
    for currency in currencies:
        currency_rate = rates.get(currency)
        if not currency_rate:
            continue
        
        # Calculate spread
        spread = currency_rate.rate - us_rate.rate
        
        # Get FX rate
        fx_pair = f"USD_{currency_rate.currency}"
        fx_rate = fx_rates.get(fx_pair)
        
        # Get FX volatility
        volatility = get_fx_volatility(currency_rate.currency)
        
        # Calculate risk-adjusted return
        risk_adjusted_return = spread / (1 + volatility / 100) if volatility > 0 else spread
        
        carry_trades.append({
            "currency": currency_rate.currency,
            "country": currency_rate.country,
            "central_bank": currency_rate.central_bank,
            "target_rate": currency_rate.rate,
            "funding_rate": us_rate.rate,
            "spread": spread,
            "fx_rate": fx_rate,
            "fx_volatility": volatility,
            "risk_adjusted_return": risk_adjusted_return,
            "signal": get_signal(spread),
        })
    
    # Sort by spread (highest first)
    carry_trades.sort(key=lambda x: x["spread"], reverse=True)
    
    return carry_trades


def get_fx_volatility(currency):
    """Get historical FX volatility"""
    volatility_map = {
        "BRL": 15.0, "TRY": 25.0, "MXN": 12.0, "INR": 8.0,
        "ZAR": 18.0, "ARS": 30.0, "CLP": 14.0, "PLN": 10.0,
        "COP": 16.0, "IDR": 12.0, "THB": 10.0, "PHP": 9.0,
    }
    return volatility_map.get(currency, 12.0)


def get_signal(spread):
    """Generate trading signal from spread"""
    if spread > 5.0:
        return "STRONG BUY"
    elif spread > 3.0:
        return "BUY"
    elif spread > 1.0:
        return "HOLD"
    elif spread > 0:
        return "WEAK"
    else:
        return "AVOID"


@app.route("/")
def index():
    """Main dashboard page"""
    return render_template("dashboard.html")


@app.route("/api/market-data")
def api_market_data():
    """API endpoint for market data"""
    market_data = get_market_data()
    
    # Convert rates to serializable format
    rates_serializable = {}
    for country, rate_data in market_data["rates"].items():
        rates_serializable[country] = {
            "country": rate_data.country,
            "currency": rate_data.currency,
            "central_bank": rate_data.central_bank,
            "rate": rate_data.rate,
            "rate_type": rate_data.rate_type,
            "last_updated": rate_data.last_updated,
            "source": rate_data.source,
            "notes": rate_data.notes,
        }
    
    return jsonify({
        "rates": rates_serializable,
        "fx_rates": market_data["fx_rates"],
        "timestamp": market_data["timestamp"],
    })


@app.route("/api/carry-trades")
def api_carry_trades():
    """API endpoint for carry trade opportunities"""
    market_data = get_market_data()
    carry_trades = calculate_carry_trades(market_data)
    return jsonify({"carry_trades": carry_trades, "timestamp": datetime.now().isoformat()})


@app.route("/api/interest-rates")
def api_interest_rates():
    """API endpoint for interest rates comparison"""
    market_data = get_market_data()
    rates = market_data["rates"]
    
    # Sort by rate (highest first)
    sorted_rates = sorted(rates.items(), key=lambda x: x[1].rate, reverse=True)
    
    rates_list = []
    for country, rate_data in sorted_rates:
        rates_list.append({
            "country": rate_data.country,
            "currency": rate_data.currency,
            "rate": rate_data.rate,
            "central_bank": rate_data.central_bank,
        })
    
    return jsonify({"rates": rates_list, "timestamp": datetime.now().isoformat()})


@app.route("/api/fx-rates")
def api_fx_rates():
    """API endpoint for FX rates"""
    market_data = get_market_data()
    return jsonify({"fx_rates": market_data["fx_rates"], "timestamp": datetime.now().isoformat()})


# -- Tick-panel inspired endpoints (Step 5) ---------------------------------
@app.route("/panel")
def panel():
    """Tick-panel inspired view."""
    if _HAS_TICK_PANEL:
        return render_template("dashboard_tick_panel.html")
    return render_template("dashboard.html")


@app.route("/api/watchlist")
def api_watchlist():
    if not _HAS_TICK_PANEL:
        return jsonify({"error": "tick-panel not available"}), 503
    group = request.args.get("group")
    view = request.args.get("view", "table")
    return jsonify(get_watchlist(group=group, view=view))


@app.route("/api/monitor/rules", methods=["GET", "POST"])
def api_monitor_rules():
    if not _HAS_TICK_PANEL:
        return jsonify({"error": "tick-panel not available"}), 503
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        try:
            rule = add_rule(
                rule_type=data.get("type", "price"),
                symbol=data.get("symbol", "USD/BRL"),
                condition=data.get("condition", "gt"),
                threshold=float(data.get("threshold", 0)),
                enabled=bool(data.get("enabled", True)),
            )
            return jsonify(rule), 201
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 400
    return jsonify({"rules": list_rules()})


@app.route("/api/monitor/alerts")
def api_monitor_alerts():
    if not _HAS_TICK_PANEL:
        return jsonify({"error": "tick-panel not available"}), 503
    return jsonify({"alerts": list_alerts(limit=int(request.args.get("limit", 50)))})


@app.route("/api/monitor/stream")
def api_monitor_stream():
    """SSE stream for real-time alerts; polling fallback is /api/monitor/alerts."""
    if not _HAS_TICK_PANEL:
        return jsonify({"error": "tick-panel not available"}), 503

    def gen():
        import time

        # send 3 heartbeats then close (demo); client reconnects
        for _ in range(3):
            alerts = list_alerts(limit=5)
            yield sse_format({"alerts": alerts, "timestamp": datetime.now().isoformat()})
            time.sleep(1)
        yield sse_format({"heartbeat": True, "timestamp": datetime.now().isoformat()})

    return Response(gen(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/abnormal")
def api_abnormal():
    if not _HAS_TICK_PANEL:
        return jsonify({"error": "tick-panel not available"}), 503
    md = get_market_data()
    # build current_rates as symbol -> rate
    current = {}
    for k, v in md["rates"].items():
        try:
            current[k] = float(v.rate)
        except Exception:
            continue
    moves = detect_abnormal(current)
    return jsonify({"abnormal": moves, "timestamp": datetime.now().isoformat()})


@app.route("/api/rotation")
def api_rotation():
    if not _HAS_TICK_PANEL:
        return jsonify({"error": "tick-panel not available"}), 503
    return jsonify(get_rotation_matrix())


@app.route("/api/backtest")
def api_backtest():
    """VectorBT backtest preview (pandas fallback if vectorbt missing)."""
    try:
        import pandas as pd

        from tradingagents.dataflows.vectorbt_backtest import VectorBTBacktest

        n = 100
        idx = pd.date_range("2024-01-01", periods=n, freq="D")
        price = pd.Series([100 + i * 0.3 for i in range(n)], index=idx)
        entries = price.pct_change() > 0.01
        exits = price.pct_change() < -0.01
        bt = VectorBTBacktest()
        res = bt.run(price, entries, exits)
        return jsonify({"total_return": res.total_return, "sharpe": res.sharpe, "max_drawdown": res.max_drawdown, "win_rate": res.win_rate, "num_trades": res.num_trades, "method": res.method})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.route("/api/doc-preview")
def api_doc_preview():
    path = request.args.get("path", "")
    if not path:
        return jsonify({"error": "path required"}), 400
    try:
        from tradingagents.dataflows.providers.registry import get_markitdown_provider

        md = get_markitdown_provider()
        if md is None:
            return jsonify({"preview": "_MarkItDown not available_", "path": path})
        text = md.convert_for_llm(path)
        return jsonify({"preview": text[:4000], "path": path})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Carry Trade Dashboard")
    parser.add_argument("--port", type=int, default=5000, help="Port to run on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    args = parser.parse_args()
    
    print(f"Starting dashboard on http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop")
    
    app.run(host=args.host, port=args.port, debug=args.debug)
