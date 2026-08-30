"""Tick-panel helpers: watchlist, monitor center, abnormal moves, rotation."""
from __future__ import annotations
import hashlib, json, time
from collections import deque
from datetime import datetime, timezone
from typing import Any

WATCHLIST_GROUPS: dict[str, list[str]] = {
    "High Yield": ["USD/BRL", "USD/TRY", "USD/ZAR"],
    "EM Basket": ["USD/BRL", "USD/MXN", "USD/INR", "USD/ZAR", "USD/CLP"],
    "Safe Carry": ["USD/PLN", "USD/THB", "USD/PHP", "USD/IDR"],
    "LatAm Focus": ["USD/BRL", "USD/MXN", "USD/CLP", "USD/COP", "USD/ARS"],
}
TICKER_META = {
    "USD/BRL": ("Brazil", 10.5, 15.0), "USD/TRY": ("Turkey", 50.0, 25.0),
    "USD/MXN": ("Mexico", 11.0, 12.0), "USD/INR": ("India", 6.5, 8.0),
    "USD/ZAR": ("South Africa", 8.25, 18.0), "USD/ARS": ("Argentina", 35.0, 30.0),
    "USD/CLP": ("Chile", 6.5, 14.0), "USD/PLN": ("Poland", 5.75, 10.0),
    "USD/COP": ("Colombia", 12.0, 16.0), "USD/IDR": ("Indonesia", 6.25, 12.0),
    "USD/THB": ("Thailand", 2.5, 10.0), "USD/PHP": ("Philippines", 6.5, 9.0),
}
_cache: dict[str, Any] = {}
_cache_ts: float = 0
CACHE_TTL_S = 30
RULE_TYPES = ("strategy", "signal", "price", "abnormal")
_rules: list[dict[str, Any]] = []
_alerts: deque[dict[str, Any]] = deque(maxlen=200)
_rule_seq = 0

def _now() -> str: return datetime.now(timezone.utc).isoformat()

def get_watchlist(group: str | None = None, view: str = "table") -> dict[str, Any]:
    global _cache, _cache_ts
    now = time.time(); key = f"{group}:{view}"
    if _cache and (now - _cache_ts) < CACHE_TTL_S and key in _cache: return _cache[key]
    if group and group in WATCHLIST_GROUPS: groups, tickers = {group: WATCHLIST_GROUPS[group]}, WATCHLIST_GROUPS[group]
    else: groups, tickers = WATCHLIST_GROUPS, sorted({t for v in WATCHLIST_GROUPS.values() for t in v})
    rows = [{"symbol": t, "country": TICKER_META.get(t, (t, None, None))[0], "rate": TICKER_META.get(t, (t, None, None))[1], "vol": TICKER_META.get(t, (t, None, None))[2]} for t in tickers]
    payload: dict[str, Any] = {"groups": groups, "tickers": rows, "view": view, "ts": _now()}
    if view == "card": payload["cards"] = [{"symbol": r["symbol"], "title": r["country"], "badge": f"{r['rate']}%"} for r in rows]
    if (now - _cache_ts) >= CACHE_TTL_S: _cache, _cache_ts = {}, now
    _cache[key] = payload
    return payload

def add_rule(rule_type: str, symbol: str, condition: str, threshold: float, enabled: bool = True) -> dict[str, Any]:
    global _rule_seq
    if rule_type not in RULE_TYPES: raise ValueError(f"type must be {RULE_TYPES}")
    _rule_seq += 1; r = {"id": _rule_seq, "type": rule_type, "symbol": symbol, "condition": condition, "threshold": float(threshold), "enabled": enabled, "created_at": _now()}
    _rules.append(r); return r

def list_rules() -> list[dict[str, Any]]: return list(_rules)
def list_alerts(limit: int = 50) -> list[dict[str, Any]]: return list(_alerts)[-limit:]
def push_alert(alert_type: str, message: str, severity: str = "info", data: dict | None = None) -> dict[str, Any]:
    a = {"id": hashlib.md5(f"{time.time()}{message}".encode()).hexdigest()[:8], "alert_type": alert_type, "message": message, "severity": severity, "data": data or {}, "timestamp": _now()}
    _alerts.append(a); return a

def evaluate_rules(market_data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if market_data is None: return []
    rates = market_data.get("rates", {}); trig: list[dict[str, Any]] = []
    for r in _rules:
        if not r.get("enabled"): continue
        sym = r["symbol"]; code = sym.split("/")[-1] if "/" in sym else sym
        obj = rates.get(code) or rates.get(sym) or rates.get(code[:2])
        val = getattr(obj, "rate", None) if obj is not None else None
        if val is None and isinstance(obj, dict): val = obj.get("rate")
        if val is None: continue
        c, thr = r["condition"], r["threshold"]
        hit = (c == "gt" and val > thr) or (c == "lt" and val < thr) or (c == "gte" and val >= thr) or (c == "lte" and val <= thr)
        if hit: trig.append(push_alert(r["type"], f"Rule #{r['id']} [{r['type']}] {sym} {c} {thr} hit: {val}", "warning" if r["type"] != "abnormal" else "critical", {"rule_id": r["id"], "value": val}))
    return trig

def detect_abnormal(current_rates: dict[str, float], history_3d: dict[str, float] | None = None, history_10d: dict[str, float] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sym, cur in current_rates.items():
        avg3 = (history_3d or {}).get(sym, cur * 0.97); avg10 = (history_10d or {}).get(sym, cur * 1.02)
        if avg3 == cur: avg3 = cur * 0.97
        if avg10 == cur: avg10 = cur * 1.02
        dev3 = abs(cur - avg3) / max(abs(avg3), 1e-9) * 100; dev10 = abs(cur - avg10) / max(abs(avg10), 1e-9) * 100
        if dev3 > 2.0 or dev10 > 5.0:
            sev = "critical" if dev3 > 5 or dev10 > 8 else "warning"
            out.append({"symbol": sym, "current": cur, "avg_3d": round(avg3, 4), "avg_10d": round(avg10, 4), "dev_3d_pct": round(dev3, 2), "dev_10d_pct": round(dev10, 2), "severity": sev})
            push_alert("abnormal", f"Abnormal {sym}: dev3 {dev3:.2f}% dev10 {dev10:.2f}%", sev, {"symbol": sym, "dev3": dev3, "dev10": dev10})
    return out

def get_rotation_matrix() -> dict[str, Any]:
    try:
        from tradingagents.chains.portfolio_manager import CarryTradePortfolioManager
        pm = CarryTradePortfolioManager(); md = pm.get_market_data(); strategies = pm.design_strategies(md); metrics = pm.calculate_portfolio_metrics(strategies)
        concepts = [{"concept": s.name, "allocation_pct": s.allocation_pct, "spread": s.spread, "expected_return": s.expected_return, "risk": s.max_drawdown} for s in strategies]
        matrix = [[c["concept"], c["allocation_pct"], c["spread"], c["expected_return"]] for c in concepts]
        return {"concepts": concepts, "matrix": matrix, "metrics": metrics, "timestamp": _now()}
    except Exception as exc:  # noqa: BLE001
        return {"concepts": [], "matrix": [], "metrics": {}, "error": str(exc), "timestamp": _now()}

def sse_format(data: dict[str, Any]) -> str: return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
