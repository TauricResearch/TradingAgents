"""命令行: 同步 / 查看 A 股本地数据。

    tradingagents-ashare sync                       全部步骤 (首次建立个股 base 需要较长时间, 可中断续传)
    tradingagents-ashare sync --only market,spot    只同步部分步骤
    tradingagents-ashare sync --refresh             忽略当日缓存, 重新拉取
    tradingagents-ashare status                     查看本地数据概况 (不访问网络)

也可以用 python -m tradingagents.dataflows.vendors.akshare <命令>。
"""
from __future__ import annotations

import argparse
import logging
import sys

from tradingagents.dataflows.vendors.akshare import settings, sync


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tradingagents-ashare", description="A 股数据 (AKShare) 下载与本地缓存")
    ap.add_argument("--data-dir", default=None,
                    help=f"数据目录 (默认 {settings.DEFAULT_DATA_DIR}; 也可用环境变量 {settings.DATA_DIR_ENV})")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("sync", help="下载 / 增量补齐数据")
    s.add_argument("--only", default="", help=f"逗号分隔的步骤, 可选: {', '.join(sync.STEPS)} (默认全部)")
    s.add_argument("--refresh", action="store_true", help="忽略当日缓存, 强制重新拉取")
    s.add_argument("--insider", action="store_true", help="额外拉取产业资本增减持 (首次较慢)")
    s.add_argument("--no-history-reports", action="store_true", help="不下载历史各报告期的业绩报表")
    s.add_argument("--allow-intraday", action="store_true", help="盘中 (15:30 前) 也保存当日个股快照")
    s.add_argument("--backfill-workers", type=int, default=4, help="补下载个股日线的并发数 (默认 4, 过高易被限流)")
    s.add_argument("--xq-codes", default="", help="新浪 / 东财都失败时用雪球查询的股票, 逗号分隔 (需 XQ_TOKEN)")
    sub.add_parser("status", help="查看本地数据概况")
    return ap


def main(argv: list[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    if a.data_dir:
        settings.set_data_dir(a.data_dir)
    if a.cmd == "status":
        df = sync.status()
        print(f"数据目录: {settings.data_dir()}")
        print(df.to_string(index=False) if len(df) else "(空)")
        return 0
    if a.cmd is None:
        a = _parser().parse_args([*(argv or sys.argv[1:]), "sync"])
    only = [x.strip() for x in a.only.split(",") if x.strip()] or None
    xq = [x.strip() for x in a.xq_codes.split(",") if x.strip()] or None
    sync.sync_all(only=only, refresh=a.refresh, with_insider=a.insider, allow_intraday=a.allow_intraday,
                  workers=a.backfill_workers, history_reports=not a.no_history_reports, xq_codes=xq)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
