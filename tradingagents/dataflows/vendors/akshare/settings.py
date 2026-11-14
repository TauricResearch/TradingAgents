"""A 股数据层的全局设置: 本地数据目录、起始日期、HTTP 超时。

数据目录 (默认: 仓库根目录下的 .akshare_data/) 的解析顺序:
    1. set_data_dir(path)                         代码里显式指定 (CLI 的 --data-dir)
    2. 环境变量 TRADINGAGENTS_AKSHARE_DATA_DIR
    3. 默认 <仓库根目录>/.akshare_data

目录结构 (与 invest_a 的 .thermo_cache 完全一致, 只是改了名字):
    .akshare_data/
        ts/                 增量时间序列 (parquet): 指数行情 / 国债 / 申万A指 / 申万行业日度估值
        snapshots/          个股日线: base/ 初始数据 + 之后每个交易日一个日期目录 (见 snapshots.py)
        spot_pages/         东方财富全市场行情的分页续传暂存
        spot_ref.parquet    新浪行情推算换手率 / 市值 / PE / PB 用的股本与每股指标
        <name>__<键>.pkl    分层缓存 (键 = 交易日 / 周 / 报告期, 见 store.cached)
        _calendar_YYYYMM.pkl 交易日历 (按月缓存)
"""
from __future__ import annotations

import os
from pathlib import Path

DATA_DIR_ENV = "TRADINGAGENTS_AKSHARE_DATA_DIR"
DATA_DIR_NAME = ".akshare_data"

# 仓库根目录: tradingagents/dataflows/vendors/akshare/settings.py -> parents[4]
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_DIR = REPO_ROOT / DATA_DIR_NAME

# 增量时间序列首次下载的起始日期
START_DATE = "20050101"

# HTTP 超时 (连接, 读取), 单位秒。akshare 内部大量使用 requests 且多数调用未显式传 timeout,
# 网络挂死时会导致进程无限期卡住; store.install_http_timeout() 把它注入到所有未指定 timeout 的请求。
HTTP_TIMEOUT = (10, 30)

_override: Path | None = None


def set_data_dir(path: str | os.PathLike | None) -> None:
    """显式指定数据目录; 传 None 恢复为环境变量 / 默认值。"""
    global _override
    _override = Path(path).expanduser().resolve() if path else None


def data_dir() -> Path:
    """当前生效的数据目录 (不创建)。"""
    if _override is not None:
        return _override
    env = os.environ.get(DATA_DIR_ENV)
    return Path(env).expanduser().resolve() if env else DEFAULT_DATA_DIR
