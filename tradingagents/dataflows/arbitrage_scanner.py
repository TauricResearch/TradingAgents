"""ArbitrageScanner: CIP deviation as cheap-asset finder (optional, not replacing carry)."""
from __future__ import annotations
import logging
import warnings
from dataclasses import asdict, dataclass

try:
    from tradingagents.dataflows.cost_model import CostModel
    _HAS_COST = True
except ImportError:
    _HAS_COST = False
    CostModel = None  # type: ignore

logger = logging.getLogger(__name__)

_CCY_TO_COUNTRY = {"USD":"US","EUR":"EU","GBP":"GB","JPY":"JP","BRL":"BR","MXN":"MX","ARS":"AR","CLP":"CL","INR":"IN","TRY":"TR","ZAR":"ZA","PLN":"PL","COP":"CO","IDR":"ID","THB":"TH","PHP":"PH","CHF":"CH","CAD":"CA","AUD":"AU","CNY":"CN"}
# CME FX futures proxies for G10 (quoted vs USD); EM NDFs not on CME, return None -> ARBITRAGED
_CME_FUTURES = {"JPY":"6J=F","GBP":"6B=F","EUR":"6E=F","CHF":"6S=F","AUD":"6A=F","CAD":"6C=F","NZD":"6N=F"}
_DEFAULT_ETF_MAP = {"BRL":"EWZ","TRY":"TUR","MXN":"EWW","ZAR":"EZA","INR":"INDA","PLN":"EPOL","COP":"GXG","CLP":"ECH","IDR":"EIDO","THB":"THD","PHP":"EPHE"}

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
        base, quote = base.upper(), quote.upper()
        # 1) CCXT spot proxy (warn: not true forward, but cheap proxy where NDF exists)
        try:
            import ccxt  # type: ignore
            for exch_id in ("binance", "coinbase", "kraken"):
                try:
                    ex_cls = getattr(ccxt, exch_id, None)
                    if ex_cls is None: continue
                    ex = ex_cls({"enableRateLimit": True, "timeout": 5000})
                    # try direct and inverse; USDT legs as last resort
                    for sym in (f"{base}/{quote}", f"{quote}/{base}", f"{base}/USDT", f"{quote}/USDT", f"USDT/{quote}", f"USDT/{base}"):
                        try:
                            tk = ex.fetch_ticker(sym)
                            last = tk.get("last") if tk else None
                            if last is None: continue
                            price = float(last)
                            if sym == f"{quote}/{base}" and price:
                                price = 1.0 / price
                            # USDT cross is not direct F, skip unless no direct pair
                            if "USDT" in sym and f"{base}/{quote}" != sym and f"{quote}/{base}" != sym:
                                # only use USDT proxy if direct failed; still proxy
                                pass
                            if price and price > 0:
                                warnings.warn(f"CCXT {exch_id} {sym}={price} as spot proxy for F_market {base}/{quote}", UserWarning)
                                logger.debug("CCXT %s %s=%.4f spot proxy for %s/%s", exch_id, sym, price, base, quote)
                                return price
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception as e:
            logger.debug("CCXT unavailable: %s", e)

        # 2) yfinance CME futures proxy (true forward-like) for G10; EM -> no future -> None
        try:
            import yfinance as yf  # type: ignore
            fut = None; invert = False
            if base == "USD" and quote in _CME_FUTURES: fut = _CME_FUTURES[quote]; invert = True
            elif quote == "USD" and base in _CME_FUTURES: fut = _CME_FUTURES[base]; invert = False
            if fut:
                try:
                    hist = yf.Ticker(fut).history(period="5d")
                    if hist is not None and not hist.empty:
                        raw = float(hist["Close"].iloc[-1])
                        price = (1.0 / raw) if invert and raw else raw
                        logger.debug("yfinance futures %s=%.4f->%.4f proxy for %s/%s", fut, raw, price, base, quote)
                        return price
                except Exception as e:
                    logger.debug("yfinance futures %s failed: %s", fut, e)
        except Exception as e:
            logger.debug("yfinance unavailable: %s", e)

        # 3) Frankfurter/FRED fallback: no public free forward curve; keep deviation 0 -> ARBITRAGED
        logger.debug("No market forward found for %s/%s", base, quote)
        return None

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
        ccy = ccy.upper()
        try:
            import yfinance as yf  # type: ignore
            tk = yf.Ticker(etf)
            hist = tk.history(period="5d")
            if hist is None or hist.empty: return None
            if len(hist) < 2: return None
            etf_ret_bps = float(hist["Close"].pct_change().dropna().iloc[-1] * 10000)
            # FX leg: USD/ccy via yfinance (e.g., USDTRY=X -> TRY per USD)
            fx_ret_bps = 0.0
            try:
                fx_ticker = f"USD{ccy}=X"
                fxt = yf.Ticker(fx_ticker)
                fh = fxt.history(period="5d")
                if fh is not None and not fh.empty and len(fh) >= 2:
                    fx_ret_bps = float(fh["Close"].pct_change().dropna().iloc[-1] * 10000)
                else:
                    # try inverse
                    inv = f"{ccy}USD=X"
                    fxt2 = yf.Ticker(inv)
                    fh2 = fxt2.history(period="5d")
                    if fh2 is not None and not fh2.empty and len(fh2) >= 2:
                        fx_ret_bps = float(-fh2["Close"].pct_change().dropna().iloc[-1] * 10000)
            except Exception:
                fx_ret_bps = 0.0
            # fallback vol
            fx_vol = None
            try: fx_vol = self.fx.get_fx_volatility("USD", ccy, days=5)
            except Exception: pass
            # ETF quoted in USD; FX up = ccy weaken -> ETF should fall if beta~1
            # disconnect = ETF move + FX move (FX-adjusted excess)
            disconnect_bps = round(etf_ret_bps + fx_ret_bps, 2)
            return {"etf": etf, "ccy": ccy, "etf_ret_bps": round(etf_ret_bps, 2), "fx_ret_bps": round(fx_ret_bps, 2), "disconnect_bps": disconnect_bps, "fx_vol": fx_vol}
        except Exception:
            return None

    def find_cheap_assets(self, threshold_bps: float = 50, pairs: list[tuple[str, str]] | None = None, etf_map: dict | None = None, tenor_m: int = 3) -> dict:
        """Cheap-asset finder: CIP deviations + ETF-FX disconnects beyond threshold."""
        arb = self.scan_all(pairs=pairs, tenor_m=tenor_m)
        cheap_arb = [r.to_dict() for r in arb if abs(r.edge_bps) > threshold_bps and r.signal != "ARBITRAGED"]
        emap = etf_map or _DEFAULT_ETF_MAP
        disc = []
        for ccy, etf in emap.items():
            try:
                d = self.etf_disconnect(etf, ccy)
                if d and abs(d.get("disconnect_bps", 0)) > threshold_bps:
                    disc.append(d)
            except Exception:
                continue
        disc.sort(key=lambda x: abs(x.get("disconnect_bps", 0)), reverse=True)
        return {"arbitrage": cheap_arb, "etf_disconnects": disc, "threshold_bps": threshold_bps, "scanned_pairs": len(arb), "cheap_count": len(cheap_arb) + len(disc)}
