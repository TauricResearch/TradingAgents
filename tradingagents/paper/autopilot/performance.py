"""Source-grounded performance scorecard; never claim an observed alpha edge."""
from __future__ import annotations
from math import isfinite
from statistics import mean


def scorecard(book) -> dict:
    history = book.equity_history
    trades = book.completed
    start = book.settings.initial_gbp
    final = book.equity()
    benchmark = history[-1]["spy_benchmark_gbp"] if history else None
    winners = [x["pnl_gbp"] for x in trades if x["pnl_gbp"] > 0]
    losers = [x["pnl_gbp"] for x in trades if x["pnl_gbp"] < 0]
    max_dd = max((float(x["drawdown"]) for x in history), default=0.0)
    pf = (sum(winners)/-sum(losers)) if losers else None
    n = len(trades)
    return {
        "strategy": "Koral Equities V3 Swing Alpha simulated portfolio",
        "price_only_benchmark": "SPY in GBP (price-only, no dividends, no benchmark trading fees)",
        "initial_gbp": start, "last_session":book.last_session,
        "sessions":len(history), "closed_trades":n,
        "equity_gbp":round(final,2), "net_return_pct":round(100*(final/start-1),3),
        "spy_benchmark_gbp":round(benchmark,2) if benchmark is not None else None,
        "spy_return_pct":round(100*(benchmark/start-1),3) if benchmark is not None else None,
        "excess_return_vs_spy_price_pct_points":round(100*(final-benchmark)/start,3)
                 if benchmark is not None else None,
        "win_rate_pct":round(100*len(winners)/n,2) if n else None,
        "gross_profit_gbp":round(sum(winners),2),
        "gross_loss_gbp":round(sum(losers),2),
        "profit_factor":round(pf,3) if pf is not None and isfinite(pf) else None,
        "mean_trade_pnl_gbp":round(mean(x["pnl_gbp"] for x in trades),2) if n else None,
        "max_observed_close_to_close_drawdown_pct":round(max_dd*100,3),
        "sample_mature":n>=100 and len(history)>=126,
        "conclusion":"RESEARCH ONLY: No statistically verified edge; 100 closed trades and six months are a minimum review gate, not sufficient proof",
        "limitations":["GBP FX changes are included in simulated valuations",
                       "Modelled slippage and fees are assumptions and may underestimate real costs",
                       "Daily-bar stops can gap and fill below the nominal stop",
                       "SPY comparison excludes dividends and benchmark trading costs",
                       "The market, research and data distributions may change"],
    }
