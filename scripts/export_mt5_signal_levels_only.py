import argparse
import json
import os
from pathlib import Path

from tradingagents.agents.utils.trade_levels_tools import suggest_trade_levels


def _mt5_common_files_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA env var not found")
    return Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files"


def _make_signal(levels: dict, *, symbol_mt5: str, risk_usd: float, max_positions: int) -> dict:
    regime = str(levels.get("regime", "unknown"))
    bias = str(levels.get("bias", "neutral")).lower()
    entry_price = levels.get("entry_price")
    stop_loss = levels.get("stop_loss")
    tp1 = levels.get("take_profit_1")
    tp2 = levels.get("take_profit_2") or levels.get("take_profit")

    if bias == "long":
        action = "BUY"
        pending_type = "BUY_STOP" if regime == "trend" else "BUY_LIMIT"
    elif bias == "short":
        action = "SELL"
        pending_type = "SELL_STOP" if regime == "trend" else "SELL_LIMIT"
    else:
        action = "HOLD"
        pending_type = "NONE"

    trailing_enabled = bool(regime == "trend" and levels.get("trailing_stop_atr_mult") is not None)
    trailing_mult = levels.get("trailing_stop_atr_mult") or 0.0

    anchors = levels.get("anchors") or {}
    atr = anchors.get("atr")

    return {
        "schema_version": 1,
        "source": "suggest_trade_levels",
        "symbol": str(symbol_mt5),
        "action": action,
        "pending_type": pending_type,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit_1": tp1,
        "take_profit_2": tp2,
        "risk_usd": float(risk_usd),
        "max_positions": int(max_positions),
        "regime": regime,
        "regime_confidence": levels.get("regime_confidence"),
        "rr_target": levels.get("rr_target"),
        "entry_condition": levels.get("entry_condition"),
        "anchors": {
            "swing_low": anchors.get("swing_low"),
            "swing_high": anchors.get("swing_high"),
            "atr": atr,
            "atr_pct": anchors.get("atr_pct"),
        },
        "trailing": {
            "enabled": trailing_enabled,
            "type": "ATR",
            "multiplier": trailing_mult,
            "activate_after_R": 1.0,
            "atr": atr,
        },
        "partial_tp": {
            "enabled": tp1 is not None and tp2 is not None,
            "tp1_fraction": 0.4,
        },
        "dca": {
            "enabled": False,
        },
        "comment": "tradingagents",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol-data", default="XAUUSD=X")
    parser.add_argument("--symbol-mt5", default="XAUUSD")
    parser.add_argument("--date", required=True, help="YYYY-mm-dd (analysis as-of)")
    parser.add_argument("--risk-usd", type=float, default=10.0)
    parser.add_argument("--max-positions", type=int, default=2)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    raw = suggest_trade_levels.invoke(
        {
            "symbol": args.symbol_data,
            "curr_date": args.date,
            "account_size": None,
            "risk_per_trade_pct": 1.0,
            "max_position_pct": 10.0,
        }
    )
    try:
        levels = json.loads(raw)
    except Exception:
        raise SystemExit(raw)

    signal = _make_signal(
        levels,
        symbol_mt5=args.symbol_mt5,
        risk_usd=float(args.risk_usd),
        max_positions=int(args.max_positions),
    )

    out_path = Path(args.out).expanduser() if args.out else (_mt5_common_files_dir() / "tradingagents_signal.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(signal, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
