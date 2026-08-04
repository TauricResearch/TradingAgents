"""下载 000001.SZ 近 5 年日线，三种复权各一份，落 parquet（CSV 兜底）。

数据通道：ak.stock_zh_a_daily（新浪通道）。
  stock_zh_a_hist 走东财通道，本机被限频封禁（Remote end closed），
  故改用新浪通道，二者复权参数语义一致（""/"qfq"/"hfq"）。
符号形式：深市加 sz 前缀，沪市加 sh 前缀。
"""

import datetime as dt
import sys
import time

import akshare as ak
import pandas as pd
from pathlib import Path

SYMBOL = "000001"
AK_SYMBOL = "sz000001"  # 新浪通道需带交易所前缀
END = dt.date.today()
START = END - dt.timedelta(days=5 * 365 + 30)
OUT = Path(__file__).resolve().parent.parent / "data"
OUT.mkdir(parents=True, exist_ok=True)

ADJUST_MAP = {
    "none": "",
    "front": "qfq",
    "back": "hfq",
}


def fetch(adj_label, adj_code):
    last_err = None
    for attempt in range(5):
        try:
            df = ak.stock_zh_a_daily(
                symbol=AK_SYMBOL,
                start_date=START.strftime("%Y%m%d"),
                end_date=END.strftime("%Y%m%d"),
                adjust=adj_code,
            )
            if df is None or len(df) == 0:
                last_err = "返回空"
                time.sleep(8)
                continue
            df = df.sort_values("date").reset_index(drop=True)
            out_parquet = OUT / f"{SYMBOL}_{adj_label}.parquet"
            try:
                df.to_parquet(out_parquet, index=False, engine="pyarrow")
                out_file = out_parquet.name
            except Exception as pe:
                out_csv = OUT / f"{SYMBOL}_{adj_label}.csv"
                df.to_csv(out_csv, index=False, encoding="utf-8-sig")
                out_file = out_csv.name
                print(f"  [兜底] parquet 失败({pe})，改写 CSV", file=sys.stderr)
            print(
                f"[{adj_label}] {len(df)} 行  "
                f"{pd.to_datetime(df['date']).min().date()} ~ "
                f"{pd.to_datetime(df['date']).max().date()}  -> {out_file}"
            )
            return df
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            print(f"[{adj_label}] 第 {attempt + 1}/5 次出错: {last_err}", file=sys.stderr)
            time.sleep(8)
    raise RuntimeError(f"下载 {adj_label} 失败: {last_err}")


if __name__ == "__main__":
    print(f"标的 {SYMBOL} ({AK_SYMBOL})  {START} ~ {END}  通道=stock_zh_a_daily(新浪)")
    dfs = {}
    for label, code in ADJUST_MAP.items():
        dfs[label] = fetch(label, code)
        time.sleep(3)
    for label, df in dfs.items():
        latest = df.iloc[-1]
        gaps = (pd.to_datetime(df["date"]).diff().dt.days > 7).sum()
        print(
            f"\n[{label} 抽查] 最新行 {latest['date']}  "
            f"收盘={latest['close']:.2f}  量={latest['volume']}"
        )
        print(f"  覆盖率: {len(df)} 个交易日  长缺口(>7天): {gaps} 段")
