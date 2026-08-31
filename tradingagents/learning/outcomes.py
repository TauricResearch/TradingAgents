"""TradeOutcomeLogger — closes the learning cycle (signal -> pnl)."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import numpy as np

_SECRET_RE = re.compile(
    r"(ALPACA_API_KEY|ALPACA_SECRET_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|GOOGLE_API_KEY|FRED_API_KEY|BYMA_TOKEN|ALPHA_VANTAGE_API_KEY|api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[^'\"\s,}\n]+['\"]?",
    re.IGNORECASE,
)

DEFAULT_PATH = Path("logs/trade_outcomes.jsonl")


def _redact(obj: object) -> object:
    if isinstance(obj, str):
        return _SECRET_RE.sub(lambda m: m.group(1) + "=***", obj)
    if isinstance(obj, dict):
        return {k: _redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


class TradeOutcomeLogger:
    """Append-only JSONL logger with stats on real outcomes."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_PATH

    def log_outcome(
        self,
        gross_spread: float,
        net_expected: float,
        forecast: float,
        real_fx_move: float,
        pnl_net: float,
        cost_breakdown: Dict | None = None,
        symbol: str = "",
        timestamp: str | None = None,
    ) -> Dict:
        ts = timestamp or datetime.now().isoformat()
        record = {
            "timestamp": ts,
            "symbol": str(symbol),
            "gross_spread": float(gross_spread),
            "net_expected": float(net_expected),
            "forecast": float(forecast),
            "real_fx_move": float(real_fx_move),
            "pnl_net": float(pnl_net),
            "cost_breakdown": dict(cost_breakdown or {}),
        }
        record = _redact(record)  # type: ignore[assignment]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        try:
            os.chmod(self.path, 0o600)
        except Exception:
            pass
        return record  # type: ignore[return-value]

    def load_outcomes(self, limit: int = 1000) -> List[Dict]:
        if not self.path.exists():
            return []
        out: List[Dict] = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
        if limit and len(out) > limit:
            out = out[-limit:]
        return out

    def compute_stats(self) -> Dict:
        rows = self.load_outcomes(limit=1000)
        if not rows:
            return {"hit_rate": 0.0, "avg_pnl": 0.0, "sharpe_real": 0.0, "cost_drag": 0.0, "forecast_error": 0.0, "count": 0}
        pnls = np.array([float(r.get("pnl_net", 0)) for r in rows], dtype=float)
        hits = float(np.mean(pnls > 0)) if len(pnls) else 0.0
        avg = float(np.mean(pnls)) if len(pnls) else 0.0
        std = float(np.std(pnls)) if len(pnls) > 1 else 0.0
        sharpe = float(avg / std * np.sqrt(252)) if std > 1e-12 else 0.0
        drags = []
        for r in rows:
            g, n = float(r.get("gross_spread", 0)), float(r.get("net_expected", 0))
            drags.append(g - n)
        cost_drag = float(np.mean(drags)) if drags else 0.0
        errs = [abs(float(r.get("forecast", 0)) - float(r.get("real_fx_move", 0))) for r in rows]
        ferr = float(np.mean(errs)) if errs else 0.0
        return {"hit_rate": hits, "avg_pnl": avg, "sharpe_real": sharpe, "cost_drag": cost_drag, "forecast_error": ferr, "count": len(rows)}
