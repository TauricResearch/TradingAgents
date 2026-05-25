import pandas as pd
import yfinance as yf


def _fmt(df: pd.DataFrame, cols, n: int = 12) -> str:
    keep = [c for c in cols if c in df.columns]
    return df[keep].head(n).to_markdown(index=False)


def get_options_chain(symbol: str, expiration: str = "") -> str:
    tk = yf.Ticker(symbol)
    exps = list(tk.options or [])
    if not exps:
        return f"No listed options found for {symbol}."
    exp = expiration if expiration in exps else exps[0]
    chain = tk.option_chain(exp)
    cols = ["strike", "lastPrice", "bid", "ask", "volume", "openInterest", "impliedVolatility"]
    return (
        f"# Options chain for {symbol} — expiry {exp}\n"
        f"Available expirations: {', '.join(exps[:8])}{' ...' if len(exps) > 8 else ''}\n\n"
        f"## Calls\n{_fmt(chain.calls.sort_values('strike'), cols)}\n\n"
        f"## Puts\n{_fmt(chain.puts.sort_values('strike'), cols)}\n"
    )


def get_options_overview(symbol: str) -> str:
    tk = yf.Ticker(symbol)
    exps = list(tk.options or [])
    if not exps:
        return f"No listed options found for {symbol}."
    exp = exps[0]
    chain = tk.option_chain(exp)
    calls, puts = chain.calls, chain.puts
    call_oi = float(calls["openInterest"].sum())
    put_oi = float(puts["openInterest"].sum())
    pcr = (put_oi / call_oi) if call_oi else float("nan")
    atm_iv = pd.concat([calls["impliedVolatility"], puts["impliedVolatility"]]).median()
    return (
        f"# Derivatives overview for {symbol}\n"
        f"- Expirations available: {len(exps)} (nearest {exp}, furthest {exps[-1]})\n"
        f"- Nearest-expiry call OI: {call_oi:,.0f} | put OI: {put_oi:,.0f}\n"
        f"- Put/Call OI ratio: {pcr:.2f}\n"
        f"- Median implied volatility (nearest expiry): {atm_iv:.1%}\n"
    )
