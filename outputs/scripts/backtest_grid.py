"""批量向量化回测金叉死叉网格，输出 ma_grid_results.csv。

策略：
- 金叉（fast MA 上穿 slow MA）建仓，死叉（fast MA 下穿 slow MA）平仓
- 前复权数据回测（A 股标准做法）

A 股真实性优化（v2）：
- T+1：信号 t 日收盘产生，t+1 日才成交（位移 1 bar）
- 成交价：次日开盘价 open（非收盘价，无未来函数）
- 成本：佣金万1.25(单边)+印花税千1(仅卖出)+过户费万0.1 ≈ 单边千0.65
  → vectorbt fees 按双边统一收，取 fees=0.00065, slippage=0.0005（偏保守）
- 涨跌停：000001 大盘银行股 5年仅2天近涨停，影响极小，未加过滤

输出：ma_grid_results.csv（含原始 v1 与优化 v2 双列对比）
"""

import json
from pathlib import Path

import pandas as pd
import vectorbt as vbt

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_DIR = Path(__file__).resolve().parent.parent / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATA_FILE = DATA_DIR / "000001_front.parquet"
GRID_FILE = DATA_DIR / "grid.json"
RESULT_FILE = OUT_DIR / "ma_grid_results.csv"

INIT_CASH = 100_000
FREQ = "D"
# A 股真实成本：佣金万2.5(双边)+印花税千1(单边卖出)+过户费万0.1
# 单边综合约 千0.65；vectorbt fees 作用于每笔成交(买卖各收一次)
FEES = 0.00065
SLIPPAGE = 0.0005


def load_data():
    df = pd.read_parquet(DATA_FILE)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df["close"].astype(float), df["open"].astype(float)


def run_grid(close, open_px, grid):
    rows = []
    # 基准：买入持有（次日开盘全仓）
    bh_pf = vbt.Portfolio.from_holding(close, init_cash=INIT_CASH, freq=FREQ)
    bh_total = float(bh_pf.total_return())
    bh_sharpe = float(bh_pf.sharpe_ratio())
    bh_maxdd = float(bh_pf.max_drawdown())
    print(f"[基准 买入持有] 总收益={bh_total:.4f} 夏普={bh_sharpe:.3f} 最大回撤={bh_maxdd:.4f}")

    for fast, slow in grid:
        fast_ma = vbt.MA.run(close, fast).ma
        slow_ma = vbt.MA.run(close, slow).ma
        entries = fast_ma.vbt.crossed_above(slow_ma)
        exits = fast_ma.vbt.crossed_below(slow_ma)

        # v1: 原始（收盘信号+收盘成交，允许T+0）
        pf_v1 = vbt.Portfolio.from_signals(
            close,
            entries=entries,
            exits=exits,
            init_cash=INIT_CASH,
            freq=FREQ,
            fees=0.001,
            slippage=0.001,
        )

        # v2: A股真实（信号位移1bar → 次日成交，T+1）
        # pandas shift(1) 把信号往后挪一天：t日信号→t+1日成交（无未来函数）
        # 注意：不能用 vbt.signals.bshift，它往前挪=未来函数
        # fillna 后强制 bool，避免 numba 报 object 类型错
        entries_s = entries.shift(1).fillna(False).astype(bool)
        exits_s = exits.shift(1).fillna(False).astype(bool)
        pf_v2 = vbt.Portfolio.from_signals(
            close,
            entries=entries_s,
            exits=exits_s,
            price=open_px,  # 次日开盘价成交
            init_cash=INIT_CASH,
            freq=FREQ,
            fees=FEES,
            slippage=SLIPPAGE,
        )

        def metrics(pf):
            trades = pf.trades.records_readable
            n = len(trades)
            wr = float((trades["PnL"] > 0).mean()) if n > 0 else 0.0
            return {
                "total_return": float(pf.total_return()),
                "annual_return": float(pf.annualized_return()),
                "sharpe": float(pf.sharpe_ratio()),
                "max_drawdown": float(pf.max_drawdown()),
                "n_trades": n,
                "win_rate": wr,
            }

        m1, m2 = metrics(pf_v1), metrics(pf_v2)
        rows.append(
            {
                "fast": fast,
                "slow": slow,
                **{f"{k}_v1": m1[k] for k in m1},
                **{f"{k}_v2": m2[k] for k in m2},
            }
        )

    res = pd.DataFrame(rows)
    res["bh_total_return"] = bh_total
    res["bh_sharpe"] = bh_sharpe
    res["bh_max_drawdown"] = bh_maxdd
    res["excess_return_v1"] = res["total_return_v1"] - bh_total
    res["excess_return_v2"] = res["total_return_v2"] - bh_total
    return res, {"bh_total_return": bh_total, "bh_sharpe": bh_sharpe, "bh_max_drawdown": bh_maxdd}


if __name__ == "__main__":
    close, open_px = load_data()
    print(
        f"数据: {close.shape[0]} 个交易日  {close.index.min().date()} ~ {close.index.max().date()}"
    )
    grid = json.loads(GRID_FILE.read_text(encoding="utf-8"))["grid"]
    print(f"网格: {len(grid)} 组  (v1原始 vs v2 T+1+次日开盘)")
    res, bh = run_grid(close, open_px, grid)
    res.to_csv(RESULT_FILE, index=False, encoding="utf-8-sig")
    print(f"\n=== 结果已存 {RESULT_FILE} ===")
    print("\n--- v2 优化版 Top5 (按 total_return_v2) ---")
    print(
        res.sort_values("total_return_v2", ascending=False)
        .head(5)[
            [
                "fast",
                "slow",
                "total_return_v1",
                "total_return_v2",
                "sharpe_v1",
                "sharpe_v2",
                "n_trades_v1",
                "n_trades_v2",
            ]
        ]
        .to_string(index=False)
    )
    print(f"\n基准买入持有: 总收益={bh['bh_total_return']:.4f} 夏普={bh['bh_sharpe']:.3f}")
    # v1 vs v2 整体对比
    print(f"\n--- v1 vs v2 整体对比 ---")
    print(
        f"v1 跑赢基准: {int((res['excess_return_v1'] > 0).sum())}/{len(res)}  v2 跑赢基准: {int((res['excess_return_v2'] > 0).sum())}/{len(res)}"
    )
    print(
        f"v1 平均交易次数: {res['n_trades_v1'].mean():.1f}  v2 平均交易次数: {res['n_trades_v2'].mean():.1f}  (T+1应使v2略低)"
    )
