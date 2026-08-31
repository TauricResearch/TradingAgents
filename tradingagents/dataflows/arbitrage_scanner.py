"""ArbitrageScanner: CIP deviation as cheap-asset finder (optional, not replacing carry)."""
from __future__ import annotations
from dataclasses import asdict, dataclass
try:
    from tradingagents.dataflows.cost_model import CostModel
    _HAS_COST = True
except ImportError:
    _HAS_COST = False
    CostModel = None  # type: ignore
_CCY_TO_COUNTRY = {"USD":"US","EUR":"EU","GBP":"GB","JPY":"JP","BRL":"BR","MXN":"MX","ARS":"AR","CLP":"CL","INR":"IN","TRY":"TR","ZAR":"ZA","PLN":"PL","COP":"CO","IDR":"ID","THB":"TH","PHP":"PH","CHF":"CH","CAD":"CA","AUD":"AU","CNY":"CN"}
@dataclass
class ScanResult:
    base: str
    quote: str
    pair: str
    spot: float | None
    theoretical_forward: float | None
    market_forward: float | None
    deviation_bps: float
    edge_bps: float
    vol: float | None
    signal: str
    cost_bps: float = 0
    def to_dict(self) -> dict:
        return asdict(self)
class ArbitrageScanner:
    """CIP deviation scanner: theoretical vs market forward."""
    def __init__(self, fx_provider=None, rates_provider=None, cost_model=None):
        if fx_provider is None:
            from tradingagents.dataflows.providers.fx_multi_currency import MultiCurrencyFXProvider
            fx_provider = MultiCurrencyFXProvider()
        if rates_provider is None:
            from tradingagents.dataflows.providers.interest_rates import GlobalInterestRatesProvider
            rates_provider = GlobalInterestRatesProvider()
        self.fx = fx_provider; self.rates = rates_provider
        self.cost_model = cost_model or (CostModel() if _HAS_COST and CostModel else None)
    @staticmethod
    def theoretical_forward(spot: float, r_fund: float, r_tgt: float, tenor_m: int = 3) -> float:
        t = tenor_m / 12.0
        return spot * (1 + r_tgt / 100 * t) / (1 + r_fund / 100 * t)
    def _market_forward(self, base: str, quote: str) -> float | None:
        try:
            import ccxt  # type: ignore
            ex = ccxt.binance({"enableRateLimit": True})
            tk = ex.fetch_ticker(f"{base}/{quote}")
            return float(tk["last"]) if tk and tk.get("last") else None
        except Exception: return None
    def _signal(self, edge_bps: float) -> str:
        ae = abs(edge_bps)
        if ae < 15: return "ARBITRAGED"
        if edge_bps > 50: return "STRONG BUY"
        if edge_bps > 15: return "BUY"
        return "WEAK"
    def scan_pair(self, base: str, quote: str, tenor_m: int = 3) -> ScanResult:
        base, quote = base.upper(), quote.upper()
        spot = None
        try:
            r = self.fx.get_rate(base, quote)
            spot = float(r.rate) if r else None
        except Exception: pass
        try:
            c_fund = _CCY_TO_COUNTRY.get(base, base[:2].upper())
            c_tgt = _CCY_TO_COUNTRY.get(quote, quote[:2].upper())
            rf = self.rates.get_rate(c_fund) or self.rates.get_rate(base)
            rt = self.rates.get_rate(c_tgt) or self.rates.get_rate(quote)
            r_fund = float(rf.rate) if rf else 3.0; r_tgt = float(rt.rate) if rt else 3.0
        except Exception: r_fund, r_tgt = 3.0, 3.0
        theo = self.theoretical_forward(spot, r_fund, r_tgt, tenor_m) if spot else None
        mkt = self._market_forward(base, quote)
        dev = ((mkt - theo) / theo * 10000) if (mkt and theo) else 0.0
        cost_bps = 0.0
        if self.cost_model is not None:
            try: cost_bps = float(self.cost_model.for_currency(quote).total_bps())
            except Exception: cost_bps = 0.0
        edge = dev - cost_bps
        vol = None
        try:
            v = self.fx.get_fx_volatility(base, quote, days=30)
            vol = float(v) if v is not None else None
        except Exception: pass
        return ScanResult(base=base, quote=quote, pair=f"{base}/{quote}", spot=spot, theoretical_forward=theo, market_forward=mkt, deviation_bps=round(dev, 2), edge_bps=round(edge, 2), vol=vol, signal=self._signal(edge), cost_bps=cost_bps)
    def scan_all(self, pairs: list[tuple[str, str]] | None = None, tenor_m: int = 3) -> list[ScanResult]:
        if pairs is None: pairs = [("USD","BRL"),("USD","TRY"),("USD","MXN"),("USD","ZAR"),("USD","PLN"),("USD","INR"),("USD","CLP"),("USD","COP")]
        out = [self.scan_pair(b, q, tenor_m) for b, q in pairs]
        out.sort(key=lambda r: r.edge_bps / (r.vol if r.vol and r.vol > 1e-9 else 1.0), reverse=True)
        return out
    def etf_disconnect(self, etf: str, ccy: str) -> dict | None:
        try:
            import yfinance as yf  # type: ignore
            tk = yf.Ticker(etf); hist = tk.history(period="5d")
            if hist is None or hist.empty: return None
            etf_ret = float(hist["Close"].pct_change().dropna().iloc[-1] * 10000) if len(hist) > 1 else 0.0
            fx_vol = None
            try: fx_vol = self.fx.get_fx_volatility("USD", ccy.upper(), days=5)
            except Exception: pass
            return {"etf": etf, "ccy": ccy.upper(), "etf_ret_bps": round(etf_ret, 2), "fx_vol": fx_vol}
        except Exception: return None
