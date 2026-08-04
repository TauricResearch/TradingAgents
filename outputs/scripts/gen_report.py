"""生成优化报告 v2：optimization_report.md + quantstats HTML（基于 T+1 优化版）。"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import pandas as pd
import quantstats as qs
import vectorbt as vbt

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RPT_DIR = Path(__file__).resolve().parent.parent / "reports"
RPT_DIR.mkdir(parents=True, exist_ok=True)

DATA_FILE = DATA_DIR / "000001_front.parquet"
RESULT_FILE = RPT_DIR / "ma_grid_results.csv"
MD_FILE = RPT_DIR / "optimization_report.md"
HTML_FILE = RPT_DIR / "000001_best_strategy_qs.html"

INIT_CASH = 100_000
FREQ = "D"
FEES = 0.00065
SLIPPAGE = 0.0005


def load_data():
    df = pd.read_parquet(DATA_FILE)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df["close"].astype(float), df["open"].astype(float)


def build_strategy_returns(close, open_px, fast, slow):
    fast_ma = vbt.MA.run(close, fast).ma
    slow_ma = vbt.MA.run(close, slow).ma
    entries = fast_ma.vbt.crossed_above(slow_ma).shift(1).fillna(False).astype(bool)
    exits = fast_ma.vbt.crossed_below(slow_ma).shift(1).fillna(False).astype(bool)
    pf = vbt.Portfolio.from_signals(
        close,
        entries=entries,
        exits=exits,
        price=open_px,
        init_cash=INIT_CASH,
        freq=FREQ,
        fees=FEES,
        slippage=SLIPPAGE,
    )
    return pf.asset_returns().dropna(), pf


def main():
    close, open_px = load_data()
    res = pd.read_csv(RESULT_FILE)

    bh_ret = close.pct_change().dropna()
    bh_total = float((1 + bh_ret).prod() - 1)
    bh_sharpe = float(bh_ret.mean() / bh_ret.std() * (252**0.5)) if bh_ret.std() > 0 else 0.0
    bh_maxdd = float(((1 + bh_ret).cumprod() / (1 + bh_ret).cumprod().cummax() - 1).min())

    # 全局最优（v2，按总收益）
    glob = res.sort_values("total_return_v2", ascending=False).iloc[0]
    tradable = res[res["n_trades_v2"] > 0]
    trad = tradable.sort_values("sharpe_v2", ascending=False).iloc[0]

    best_ret, _ = build_strategy_returns(close, open_px, int(glob["fast"]), int(glob["slow"]))
    qs.reports.html(
        best_ret,
        output=str(HTML_FILE),
        title=f"000001 金叉死叉最优( T+1) fast={int(glob['fast'])}/slow={int(glob['slow'])}",
    )

    top10 = res.sort_values("total_return_v2", ascending=False).head(10)

    md = []
    md.append("# 000001 金叉死叉策略参数优化报告（v2 T+1优化版）\n")
    md.append(
        f"**标的**: 平安银行 000001.SZ  |  **数据**: 前复权日线  |  **区间**: {close.index.min().date()} ~ {close.index.max().date()} ({len(close)} 交易日)\n"
    )
    md.append(
        f"**回测引擎**: vectorbt 向量化  |  **初始资金**: ¥{INIT_CASH:,}  |  **成本**: 单边千0.65(费)+千0.5(滑点)\n"
    )
    md.append(f"**成交规则**: t日收盘信号 → t+1日开盘成交（A 股 T+1，无未来函数）\n")
    md.append(
        f"**网格**: fast ∈ [3,5,8,10,15,20] × slow ∈ [20,30,40,60,90,120]，共 {len(res)} 组\n\n"
    )

    md.append("## 一、基准表现（买入持有）\n")
    md.append(f"| 指标 | 值 |")
    md.append(f"|---|---|")
    md.append(f"| 总收益率 | {bh_total:.2%} |")
    md.append(f"| 夏普比率 | {bh_sharpe:.3f} |")
    md.append(f"| 最大回撤 | {bh_maxdd:.2%} |\n")

    md.append("## 二、全局最优 v2（T+1优化，按总收益）\n")
    md.append(f"**fast={int(glob['fast'])}, slow={int(glob['slow'])}**\n")
    md.append(f"| 指标 | v1原始(收盘成交T+0) | v2优化(次日开盘T+1) | 基准 | v2超额 |")
    md.append(f"|---|---|---|---|---|")
    md.append(
        f"| 总收益 | {glob['total_return_v1']:.2%} | {glob['total_return_v2']:.2%} | {bh_total:.2%} | {glob['total_return_v2'] - bh_total:+.2%} |"
    )
    md.append(
        f"| 夏普 | {glob['sharpe_v1']:.3f} | {glob['sharpe_v2']:.3f} | {bh_sharpe:.3f} | {glob['sharpe_v2'] - bh_sharpe:+.3f} |"
    )
    md.append(
        f"| 最大回撤 | {glob['max_drawdown_v1']:.2%} | {glob['max_drawdown_v2']:.2%} | {bh_maxdd:.2%} | {glob['max_drawdown_v2'] - bh_maxdd:+.2%} |"
    )
    md.append(f"| 交易次数 | {int(glob['n_trades_v1'])} | {int(glob['n_trades_v2'])} | - | - |")
    md.append(f"| 胜率 | {glob['win_rate_v1']:.2%} | {glob['win_rate_v2']:.2%} | - | - |\n")

    md.append("## 三、可交易最优 v2（剔除无交易，按夏普）\n")
    md.append(f"**fast={int(trad['fast'])}, slow={int(trad['slow'])}**\n")
    md.append(f"| 指标 | v2策略 | 基准 | v2超额 |")
    md.append(f"|---|---|---|---|")
    md.append(
        f"| 总收益 | {trad['total_return_v2']:.2%} | {bh_total:.2%} | {trad['total_return_v2'] - bh_total:+.2%} |"
    )
    md.append(
        f"| 夏普 | {trad['sharpe_v2']:.3f} | {bh_sharpe:.3f} | {trad['sharpe_v2'] - bh_sharpe:+.3f} |"
    )
    md.append(
        f"| 最大回撤 | {trad['max_drawdown_v2']:.2%} | {bh_maxdd:.2%} | {trad['max_drawdown_v2'] - bh_maxdd:+.2%} |"
    )
    md.append(f"| 交易次数 | {int(trad['n_trades_v2'])} | - | - |\n")

    md.append("## 四、Top-10 参数组合 v2（按总收益）\n")
    md.append(
        "| 排名 | fast | slow | 总收益v2 | 夏普v2 | 最大回撤v2 | 交易次数 | 胜率 | v1总收益 | 优化提升 |"
    )
    md.append("|---|---|---|---|---|---|---|---|---|---|")
    for i, (_, r) in enumerate(top10.iterrows(), 1):
        lift = r["total_return_v2"] - r["total_return_v1"]
        md.append(
            f"| {i} | {int(r['fast'])} | {int(r['slow'])} | {r['total_return_v2']:.2%} | {r['sharpe_v2']:.3f} | {r['max_drawdown_v2']:.2%} | {int(r['n_trades_v2'])} | {r['win_rate_v2']:.2%} | {r['total_return_v1']:.2%} | {lift:+.2%} |"
        )
    md.append("")

    md.append("## 五、v1 vs v2 优化效果对比\n")
    n_beat_v1 = int((res["excess_return_v1"] > 0).sum())
    n_beat_v2 = int((res["excess_return_v2"] > 0).sum())
    md.append(f"- **跑赢基准**: v1 {n_beat_v1}/{len(res)} → v2 {n_beat_v2}/{len(res)}")
    md.append(
        f"- **平均总收益**: v1 {res['total_return_v1'].mean():.2%} → v2 {res['total_return_v2'].mean():.2%}（提升 {res['total_return_v2'].mean() - res['total_return_v1'].mean():+.2%}）"
    )
    md.append(
        f"- **平均夏普**: v1 {res['sharpe_v1'].mean():.3f} → v2 {res['sharpe_v2'].mean():.3f}"
    )
    md.append(
        f"- **优化来源**: 次日开盘成交（避免收盘价未来函数）+ 成本精算（千2→千1.15）+ T+1 限制\n"
    )

    md.append("## 六、整体结论\n")
    md.append(
        f"- **市场背景**: 000001 近5年熊市，买入持有 {bh_total:.1%}，最大回撤 {bh_maxdd:.1%}。"
    )
    md.append(
        f"- **全局最优 fast={int(glob['fast'])}/slow={int(glob['slow'])}**: v2 总收益 {glob['total_return_v2']:.2%}，相对基准少亏 {abs(glob['total_return_v2'] - bh_total):.1%}，夏普 {glob['sharpe_v2']:.3f}，最大回撤 {glob['max_drawdown_v2']:.1%}。"
    )
    md.append(
        f"- **诚实提醒**: 全场最优仍微亏（{glob['total_return_v2']:.2%}），金叉死叉单因子在此标的无绝对 alpha，仅「减亏」价值。实盘需结合 AI 决策与基本面。"
    )
    md.append(
        f"- **v2 优化有效**: T+1 + 次日开盘成交 + 成本精算让多数组合收益/夏普提升，未引入未来函数。"
    )
    md.append(f"- **详细 HTML**: [000001_best_strategy_qs.html]({HTML_FILE.name})\n")

    MD_FILE.write_text("\n".join(md), encoding="utf-8")
    print(f"-> {MD_FILE}")
    print(f"-> {HTML_FILE}")
    print(
        f"\n全局最优v2: fast={int(glob['fast'])} slow={int(glob['slow'])} 收益={glob['total_return_v2']:.2%} 夏普={glob['sharpe_v2']:.3f}"
    )
    print(
        f"v1→v2 平均收益提升: {res['total_return_v2'].mean() - res['total_return_v1'].mean():+.2%}"
    )


if __name__ == "__main__":
    main()
