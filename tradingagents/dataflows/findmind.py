# -*- coding: utf-8 -*-
"""
此檔案為向後相容的別名模組。

正確的模組名稱為 finmind（不是 findmind）。
請改用：from tradingagents.dataflows import finmind
"""

# 重新匯出所有 finmind 模組的內容
from .finmind import *

# 發出棄用警告
import warnings
warnings.warn(
    "模組名稱 'findmind' 已棄用，請改用 'finmind'。"
    "例如：from tradingagents.dataflows import finmind",
    DeprecationWarning,
    stacklevel=2
)
