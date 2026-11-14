"""A 股数据 (AKShare): 下载并缓存到本地 .akshare_data/, 供 A 股分析使用。

从 invest_a 的 a_thermo 数据层移植而来, 本地目录结构与原 .thermo_cache 相同。

模块:
    settings    数据目录 (.akshare_data / TRADINGAGENTS_AKSHARE_DATA_DIR)、起始日期、HTTP 超时
    store       akshare 入口、交易日历、分层缓存 (cached)、增量序列 (incremental)、代码工具
    market      市场层面: 指数、国债、申万A指估值、两融、QVIX、宏观、新发基金、增减持
    industry    申万一级 / 二级行业: 列表、日度估值、成分股
    financials  业绩报表、分红送配、历史业绩报表
    spot        全市场实时行情 (新浪 -> 东方财富 -> 雪球)
    snapshots   个股日线快照 (base + 每日目录) 的更新与读取
    sync        一次同步全部步骤; status() 查看本地数据概况
    cli         命令行 (tradingagents-ashare / python -m tradingagents.dataflows.vendors.akshare)

akshare 只在真正下载时才导入 (store.ak()), 只读取本地数据不需要网络。
"""
from tradingagents.dataflows.vendors.akshare.settings import data_dir, set_data_dir
from tradingagents.dataflows.vendors.akshare.snapshots import (
    load_cross_section,
    load_daily,
    load_stock,
)
from tradingagents.dataflows.vendors.akshare.store import (
    exchange_prefix,
    last_closed_trade_date,
    to_symbol,
    trade_calendar,
)
from tradingagents.dataflows.vendors.akshare.sync import STEPS, status, sync_all
