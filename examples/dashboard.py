"""
Carry Trade Dashboard
=====================
Web-based monitoring dashboard for carry trade portfolio.

Usage:
    python examples/dashboard.py
    python examples/dashboard.py --port 8080
"""

import functools
import math
import os
import re
import sys
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradingagents.dataflows.providers.fx_multi_currency import MultiCurrencyFXProvider
from tradingagents.dataflows.providers.interest_rates import GlobalInterestRatesProvider

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

# Security: token auth
_DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "")

# Rate limiting: try Flask-Limiter, fallback to manual in-memory
_HAS_LIMITER = False
try:
    from flask_limiter import Limiter  # type: ignore
    from flask_limiter.util import get_remote_address  # type: ignore

    limiter = Limiter(get_remote_address, app=app, default_limits=["60 per minute"])
    _HAS_LIMITER = True
except Exception:
    _HAS_LIMITER = False
    _RATE_BUCKETS: dict[str, deque] = defaultdict(deque)
    _RATE_LIMIT = 60
    _RATE_WINDOW = 60

# Validation constants
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,10}/[A-Z0-9]{2,10}$")
_CONDITION_ALLOW = {"gt", "lt", "gte", "lte", "eq", "ne"}
_VIEW_ALLOW = {"table", "card"}
_ALLOWED_SUFFIXES = {".pdf", ".md", ".csv", ".xlsx", ".html", ".txt", ".json", ".pptx", ".zip"}
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ALLOWED_DIRS = [_PROJECT_ROOT / "docs", _PROJECT_ROOT / "data", _PROJECT_ROOT / "examples"]

# Initialize providers
rates_provider = GlobalInterestRatesProvider()
fx_provider = MultiCurrencyFXProvider()


def require_token(fn):
    """Require DASHBOARD_TOKEN via X-Auth-Token header or ?token query."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if _DASHBOARD_TOKEN:
            token = request.headers.get("X-Auth-Token") or request.args.get("token", "")
            if token != _DASHBOARD_TOKEN:
                return jsonify({"error": "unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


@app.before_request
def _auth_and_rate_limit():
    # Rate limit for /api/* (manual fallback)
    if request.path.startswith("/api/") and not _HAS_LIMITER:
        ip = request.remote_addr or "unknown"
        now = time.time()
        bucket = _RATE_BUCKETS[ip]
        # prune
        while bucket and now - bucket[0] > _RATE_WINDOW:
            bucket.popleft()
        if len(bucket) >= _RATE_LIMIT:
            return jsonify({"error": "rate limit exceeded"}), 429
        bucket.append(now)
    # Token auth for /api/*
    if request.path.startswith("/api/") and _DASHBOARD_TOKEN:
        token = request.headers.get("X-Auth-Token") or request.args.get("token", "")
        if token != _DASHBOARD_TOKEN:
            return jsonify({"error": "unauthorized"}), 401


@app.after_request
def _security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    return resp


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
@require_token
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
@require_token
def api_carry_trades():
    """API endpoint for carry trade opportunities"""
    market_data = get_market_data()
    carry_trades = calculate_carry_trades(market_data)
    return jsonify({"carry_trades": carry_trades, "timestamp": datetime.now().isoformat()})


@app.route("/api/arbitrage")
@app.route("/api/arbitrage/scan")
@require_token
def api_arbitrage():
    """CIP deviation scanner (optional cheap-asset finder)."""
    try:
        from tradingagents.dataflows.arbitrage_scanner import ArbitrageScanner
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500
    try:
        tenor_m = int(request.args.get("tenor_m", "3"))
    except ValueError:
        return jsonify({"error": "tenor_m must be integer"}), 400
    if tenor_m < 1 or tenor_m > 12:
        return jsonify({"error": "tenor_m must be between 1 and 12"}), 400
    try:
        scanner = ArbitrageScanner(fx_provider=fx_provider, rates_provider=rates_provider)
        results = scanner.scan_all(tenor_m=tenor_m)
        return jsonify({"results": [r.to_dict() for r in results], "timestamp": datetime.now().isoformat()})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.route("/api/interest-rates")
@require_token
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
@require_token
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
@require_token
def api_watchlist():
    if not _HAS_TICK_PANEL:
        return jsonify({"error": "tick-panel not available"}), 503
    group = request.args.get("group")
    view = request.args.get("view", "table")
    # validation: group/view allowlist
    if view not in _VIEW_ALLOW:
        return jsonify({"error": f"view must be one of {sorted(_VIEW_ALLOW)}"}), 400
    if group is not None:
        try:
            from tradingagents.dashboard import WATCHLIST_GROUPS
            if group not in WATCHLIST_GROUPS:
                return jsonify({"error": f"unknown group {group}"}), 400
        except Exception:
            pass
    return jsonify(get_watchlist(group=group, view=view))


@app.route("/api/monitor/rules", methods=["GET", "POST"])
@require_token
def api_monitor_rules():
    if not _HAS_TICK_PANEL:
        return jsonify({"error": "tick-panel not available"}), 503
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        # validation
        symbol = str(data.get("symbol", "USD/BRL"))
        if not _SYMBOL_RE.match(symbol):
            return jsonify({"error": "invalid symbol, expected e.g. USD/BRL"}), 400
        condition = str(data.get("condition", "gt"))
        if condition not in _CONDITION_ALLOW:
            return jsonify({"error": f"condition must be one of {sorted(_CONDITION_ALLOW)}"}), 400
        try:
            threshold = float(data.get("threshold", 0))
        except Exception:
            return jsonify({"error": "threshold must be numeric"}), 400
        if not math.isfinite(threshold):
            return jsonify({"error": "threshold must be finite"}), 400
        try:
            rule = add_rule(
                rule_type=data.get("type", "price"),
                symbol=symbol,
                condition=condition,
                threshold=threshold,
                enabled=bool(data.get("enabled", True)),
            )
            return jsonify(rule), 201
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 400
    return jsonify({"rules": list_rules()})


@app.route("/api/monitor/alerts")
@require_token
def api_monitor_alerts():
    if not _HAS_TICK_PANEL:
        return jsonify({"error": "tick-panel not available"}), 503
    raw = request.args.get("limit", "50")
    try:
        limit = int(raw)
    except ValueError:
        return jsonify({"error": "limit must be integer"}), 400
    if limit < 1 or limit > 100:
        return jsonify({"error": "limit must be between 1 and 100"}), 400
    return jsonify({"alerts": list_alerts(limit=limit)})


@app.route("/api/monitor/stream")
@require_token
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
@require_token
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
@require_token
def api_rotation():
    if not _HAS_TICK_PANEL:
        return jsonify({"error": "tick-panel not available"}), 503
    return jsonify(get_rotation_matrix())


@app.route("/api/backtest")
@require_token
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
@require_token
def api_doc_preview():
    path = request.args.get("path", "")
    if not path:
        return jsonify({"error": "path required"}), 400
    # path traversal guard
    if os.path.isabs(path):
        return jsonify({"error": "absolute paths not allowed"}), 400
    if ".." in Path(path).parts:
        return jsonify({"error": "path traversal not allowed"}), 400
    suffix = Path(path).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        return jsonify({"error": f"suffix not allowed {suffix}"}), 400
    try:
        resolved = (_PROJECT_ROOT / path).resolve()
        if not any(str(resolved).startswith(str(d.resolve())) for d in _ALLOWED_DIRS):
            return jsonify({"error": "path not in allowed directories"}), 400
        # block symlink escape double-check
        if not resolved.exists():
            # allow missing? Still block if outside allowed dirs already checked
            pass
        from tradingagents.dataflows.providers.registry import get_markitdown_provider

        md = get_markitdown_provider()
        if md is None:
            return jsonify({"preview": "_MarkItDown not available_", "path": path})
        text = md.convert_for_llm(str(resolved))
        return jsonify({"preview": text[:4000], "path": path})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Carry Trade Dashboard")
    parser.add_argument("--port", type=int, default=5000, help="Port to run on")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--allow-public", action="store_true", help="Allow binding to 0.0.0.0")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode (only on 127.0.0.1)")

    args = parser.parse_args()

    if args.host == "0.0.0.0" and not args.allow_public:
        parser.error("binding to 0.0.0.0 requires --allow-public")
    if args.debug and args.host != "127.0.0.1":
        parser.error("--debug only allowed with --host 127.0.0.1")

    print(f"Starting dashboard on http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop")

    app.run(host=args.host, port=args.port, debug=args.debug)
