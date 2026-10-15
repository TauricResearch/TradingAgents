"""Local portfolio tracking and broker-neutral decision support."""

from __future__ import annotations

import json
import re
import tempfile
from datetime import UTC, date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from tradingagents.default_config import DEFAULT_CONFIG


class Holding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, max_length=32)
    market: str
    shares: float = Field(gt=0)
    average_purchase_price: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    purchase_date: date
    notes: str | None = Field(default=None, max_length=1000)
    status: str = Field(default="OPEN", min_length=1, max_length=32)

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value: Any) -> str:
        ticker = str(value).strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-^=]{0,31}", ticker):
            raise ValueError("ticker contains unsupported characters")
        return ticker

    @field_validator("market", mode="before")
    @classmethod
    def validate_market(cls, value: Any) -> str:
        market = str(value).strip().upper()
        if market not in {"UK", "USA"}:
            raise ValueError("market must be UK or USA")
        return market

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: Any) -> str:
        currency = str(value).strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("currency must be a three-letter code")
        return currency

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> str:
        return str(value).strip().upper() or "OPEN"


class DecisionThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profit_target_pct: float = Field(default=10.0, ge=0, le=1000)
    max_loss_pct: float = Field(default=2.0, ge=0, le=100)


class PortfolioDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1)
    thresholds: DecisionThresholds = Field(default_factory=DecisionThresholds)
    holdings: list[Holding] = Field(default_factory=list)
    updated_at: str | None = None


def default_portfolio_path() -> Path:
    return Path(DEFAULT_CONFIG["results_dir"]) / "portfolio.json"


class PortfolioStore:
    """Validated, atomic persistence for the local portfolio document."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_portfolio_path()

    def load(self) -> PortfolioDocument:
        if not self.path.exists():
            return PortfolioDocument()
        try:
            return PortfolioDocument.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"portfolio file {self.path} is not usable: {exc}") from exc

    def save(self, document: PortfolioDocument) -> PortfolioDocument:
        document = PortfolioDocument.model_validate(document)
        document.updated_at = datetime.now(UTC).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(prefix=".portfolio-", suffix=".json", dir=self.path.parent)
        try:
            with open(handle, "w", encoding="utf-8") as stream:
                stream.write(document.model_dump_json(indent=2))
                stream.write("\n")
            Path(temp_name).replace(self.path)
        finally:
            temp_path = Path(temp_name)
            if temp_path.exists():
                temp_path.unlink()
        return document

    def add(self, holding: Holding) -> PortfolioDocument:
        document = self.load()
        if any(item.ticker == holding.ticker for item in document.holdings):
            raise ValueError(f"holding {holding.ticker} already exists")
        document.holdings.append(holding)
        return self.save(document)

    def update(self, ticker: str, changes: dict[str, Any]) -> PortfolioDocument:
        document = self.load()
        key = ticker.strip().upper()
        for index, existing in enumerate(document.holdings):
            if existing.ticker == key:
                payload = existing.model_dump()
                payload.update(changes)
                document.holdings[index] = Holding.model_validate(payload)
                return self.save(document)
        raise KeyError(key)

    def remove(self, ticker: str) -> PortfolioDocument:
        document = self.load()
        key = ticker.strip().upper()
        remaining = [item for item in document.holdings if item.ticker != key]
        if len(remaining) == len(document.holdings):
            raise KeyError(key)
        document.holdings = remaining
        return self.save(document)

    def set_thresholds(self, thresholds: DecisionThresholds) -> PortfolioDocument:
        document = self.load()
        document.thresholds = thresholds
        return self.save(document)


def holding_metrics(holding: Holding, current_price: float | None) -> dict[str, float] | None:
    """Calculate P/L only when an explicit positive current price is available."""
    if current_price is None or current_price <= 0:
        return None
    cost = holding.shares * holding.average_purchase_price
    value = holding.shares * current_price
    return {
        "current_price": current_price,
        "cost_basis": cost,
        "market_value": value,
        "profit_loss": value - cost,
        "profit_loss_pct": ((current_price / holding.average_purchase_price) - 1) * 100,
    }


def action_for_holding(
    holding: Holding,
    current_price: float | None,
    thresholds: DecisionThresholds,
) -> str:
    metrics = holding_metrics(holding, current_price)
    if metrics is None:
        return "WATCH"
    if metrics["profit_loss_pct"] >= thresholds.profit_target_pct:
        return "TAKE PROFIT"
    if metrics["profit_loss_pct"] <= -thresholds.max_loss_pct:
        return "REVIEW SELL"
    return "HOLD"


def _market_for_ticker(ticker: str) -> str | None:
    if ticker.upper().endswith(".L"):
        return "UK"
    if "." not in ticker:
        return "USA"
    return None


def latest_report_candidates(results_dir: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Find one latest report candidate per market; absent data stays unavailable."""
    root = Path(results_dir or DEFAULT_CONFIG["results_dir"]) / "reports"
    candidates: dict[str, dict[str, Any]] = {}
    if not root.exists():
        return candidates
    reports = sorted(
        root.glob("*/complete_report.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for report in reports:
        try:
            text = report.read_text(encoding="utf-8")
        except OSError:
            continue
        ticker_match = re.search(r"^# Trading Analysis Report: ([^\s]+)", text, re.MULTILINE)
        rating_match = re.search(r"^- Rating: (.+)$", text, re.MULTILINE)
        if not ticker_match or not rating_match:
            continue
        ticker = ticker_match.group(1).upper()
        market = _market_for_ticker(ticker)
        if not market or market in candidates:
            continue
        rating = rating_match.group(1).strip()
        upper_rating = rating.upper()
        action = (
            "REVIEW SELL" if "SELL" in upper_rating
            else "WATCH" if "BUY" in upper_rating
            else "HOLD" if "HOLD" in upper_rating
            else "WATCH"
        )
        candidates[market] = {
            "ticker": ticker,
            "market": market,
            "action": action,
            "rating": rating,
            "source": str(report),
        }
    return candidates


def decision_snapshot(
    document: PortfolioDocument,
    current_prices: dict[str, float] | None = None,
    results_dir: str | Path | None = None,
) -> dict[str, Any]:
    prices = {ticker.upper(): price for ticker, price in (current_prices or {}).items()}
    holdings = []
    for holding in document.holdings:
        current_price = prices.get(holding.ticker)
        holdings.append({
            **holding.model_dump(mode="json"),
            "metrics": holding_metrics(holding, current_price),
            "action": action_for_holding(holding, current_price, document.thresholds),
        })
    candidates = latest_report_candidates(results_dir)
    return {
        "thresholds": document.thresholds.model_dump(),
        "holdings": holdings,
        "candidates": {
            "UK": candidates.get("UK", {"available": False}),
            "USA": candidates.get("USA", {"available": False}),
        },
        "disclaimer": (
            "Decision-support only: thresholds are configurable targets, not guarantees. "
            "No trades are placed automatically."
        ),
    }


HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>TradingAgents portfolio</title>
<style>body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem}
table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:.5rem;text-align:left}
.notice{background:#fff4ce;padding:1rem}</style></head>
<body><h1>TradingAgents portfolio</h1>
<p class="notice">Decision-support only. Targets are not guarantees and this dashboard never places trades.</p>
<p>Manage holdings using the JSON API at <code>/api/portfolio</code> and view decisions at
<code>/api/decisions</code>.</p><div id="app">Loading...</div>
<script>
fetch('/api/decisions').then(r=>r.json()).then(data=>{
 const rows=data.holdings.map(h=>`<tr><td>${h.ticker}</td><td>${h.market}</td><td>${h.shares}</td><td>${h.average_purchase_price} ${h.currency}</td><td>${h.metrics ? h.metrics.profit_loss_pct.toFixed(2)+'%' : 'Unavailable'}</td><td>${h.action}</td></tr>`).join('');
 document.querySelector('#app').innerHTML=`<h2>Holdings</h2><table><tr><th>Ticker</th><th>Market</th><th>Shares</th><th>Average price</th><th>P/L</th><th>Action</th></tr>${rows||'<tr><td colspan="6">No holdings yet.</td></tr>'}</table><h2>Daily candidates</h2><p>UK: ${data.candidates.UK.available===false?'Unavailable':data.candidates.UK.ticker+' ('+data.candidates.UK.action+')'}</p><p>USA: ${data.candidates.USA.available===false?'Unavailable':data.candidates.USA.ticker+' ('+data.candidates.USA.action+')'}</p>`;
});
</script></body></html>"""


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def make_handler(store: PortfolioStore):
    class DashboardHandler(BaseHTTPRequestHandler):
        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

        def do_GET(self):  # noqa: N802
            path = urlparse(self.path).path
            if path == "/":
                body = HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/portfolio":
                _json_response(self, 200, store.load().model_dump(mode="json"))
            elif path == "/api/decisions":
                _json_response(
                    self,
                    200,
                    decision_snapshot(store.load(), results_dir=store.path.parent),
                )
            else:
                _json_response(self, 404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            path = urlparse(self.path).path
            try:
                body = self._body()
                if path == "/api/portfolio/thresholds":
                    result = store.set_thresholds(DecisionThresholds.model_validate(body))
                elif path == "/api/portfolio":
                    result = store.add(Holding.model_validate(body))
                else:
                    _json_response(self, 404, {"error": "not found"})
                    return
                _json_response(self, 200, result.model_dump(mode="json"))
            except (ValueError, ValidationError, json.JSONDecodeError) as exc:
                _json_response(self, 400, {"error": str(exc)})

        def do_PUT(self):  # noqa: N802
            try:
                result = store.update(
                    urlparse(self.path).path.rsplit("/", 1)[-1],
                    self._body(),
                )
                _json_response(self, 200, result.model_dump(mode="json"))
            except (KeyError, ValueError, ValidationError, json.JSONDecodeError) as exc:
                status = 404 if isinstance(exc, KeyError) else 400
                _json_response(self, status, {"error": str(exc)})

        def do_DELETE(self):  # noqa: N802
            try:
                result = store.remove(urlparse(self.path).path.rsplit("/", 1)[-1])
                _json_response(self, 200, result.model_dump(mode="json"))
            except KeyError as exc:
                _json_response(self, 404, {"error": str(exc)})

        def log_message(self, *_args):
            return

    return DashboardHandler


def serve_dashboard(
    host: str = "127.0.0.1",
    port: int = 8765,
    path: str | Path | None = None,
) -> None:
    """Run the local dashboard until interrupted."""
    store = PortfolioStore(path)
    server = ThreadingHTTPServer((host, port), make_handler(store))
    print(f"TradingAgents dashboard: http://{host}:{port} (portfolio: {store.path})")
    try:
        server.serve_forever()
    finally:
        server.server_close()
