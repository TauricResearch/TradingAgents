"""
5级评级系统 —— 标准化的投资评级词汇和确定性解析器

在项目中的角色：
  - 为整个系统提供统一的评级标准（Buy/Overweight/Hold/Underweight/Sell）
  - 从 LLM 生成的自然语言文本中提取结构化评级信号
  - 被多个模块共用，确保评级语义的一致性

使用方：
  - Research Manager：投资计划推荐
  - Portfolio Manager：最终仓位决策
  - SignalProcessor：提取评级供下游消费
  - MemoryLog：存储决策记录时的标签字段

设计原则：
  - 单一源：所有评级相关逻辑集中于此，避免多份定义导致的漂移
  - 健壮性：解析器能容忍 LLM 输出的格式差异（markdown、大小写等）
  - 确定性：纯正则匹配，不依赖 LLM，保证结果可预测

评级刻度（从看多到看空）：
  Buy > Overweight > Hold > Underweight > Sell
"""

from __future__ import annotations

import re
from typing import Tuple


# 标准 5 级评级刻度 —— 从最强看多到最强看空
# 这个元组是系统中评级的唯一权威定义
RATINGS_5_TIER: Tuple[str, ...] = (
    "Buy",           # 买入 —— 强烈看多，建议立即建仓
    "Overweight",    # 增持/超配 —— 看多，建议高于基准配置
    "Hold",          # 持有 —— 中性，维持现有仓位
    "Underweight",   # 减持/低配 —— 看空，建议低于基准配置
    "Sell",          # 卖出 —— 强烈看空，建议清仓或做空
)

# 小写集合，用于快速查找匹配（O(1) 时间复杂度）
_RATING_SET = {r.lower() for r in RATINGS_5_TIER}

# 正则表达式：匹配 "Rating: X" 或 "rating - X" 模式
# 设计要点：
#   - re.IGNORECASE：忽略大小写（Rating/rating/RATING）
#   - .*?[:\-]：匹配冒号或连字符分隔符
#   - [\s*]*：容忍分隔符后的空格或 markdown 星号
#   - (\w+)：捕获评级单词（Buy/Hold/Sell 等）
#
# 可匹配的格式示例：
#   - "Rating: Buy"
#   - "rating: **Hold**"（支持 markdown 粗体）
#   - "Recommendation - Sell"
#   - "RATING:   Underweight"（容忍多余空格）
_RATING_LABEL_RE = re.compile(r"rating.*?[:\-][\s*]*(\w+)", re.IGNORECASE)


def parse_rating(text: str, default: str = "Hold") -> str:
    """从自然语言文本中启发式提取 5 级评级。

    两阶段解析策略（优先级从高到低）：
    
    阶段 1：明确标签匹配
      - 优先查找 "Rating: X" 格式的明确标注
      - 这是 Portfolio Manager 结构化输出的标准格式
      - 匹配到则立即返回，不再继续搜索
    
    阶段 2：自由文本扫描
      - 如果没有找到明确标签，扫描文本中所有单词
      - 清理 markdown 格式符号后检查是否为合法评级词
      - 返回第一个匹配的评级
    
    阶段 3：默认值兜底
      - 如果以上都没找到，返回默认值 Hold（中性）
      - 避免返回 None 导致下游错误

    Args:
        text: LLM 生成的决策文本，可能包含 markdown 格式
        default: 未找到评级时的默认返回值，默认为 "Hold"

    Returns:
        Title 格式的评级字符串（如 "Buy"、"Hold"、"Sell"）

    示例：
        >>> parse_rating("FINAL DECISION:\\nRating: **Buy**\\n理由：...")
        "Buy"
        >>> parse_rating("建议持有该股票")
        "Hold"
        >>> parse_rating("没有明确评级", default="Hold")
        "Hold"
    """
    # 阶段 1：查找明确的 "Rating: X" 标签（优先级最高）
    for line in text.splitlines():
        # 使用正则匹配标签行
        m = _RATING_LABEL_RE.search(line)
        # 检查捕获的单词是否在合法评级集合中
        if m and m.group(1).lower() in _RATING_SET:
            # 返回标题化格式（首字母大写）
            return m.group(1).capitalize()

    # 阶段 2：回退到自由文本扫描
    for line in text.splitlines():
        # 按空格分割单词，转为小写
        for word in line.lower().split():
            # 清理可能的 markdown 格式符号（*、:、.、,）
            clean = word.strip("*:.,")
            # 检查是否为合法评级
            if clean in _RATING_SET:
                return clean.capitalize()

    # 阶段 3：未找到任何评级，返回默认值
    return default
