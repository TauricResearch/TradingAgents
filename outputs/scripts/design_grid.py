"""金叉死叉策略参数网格设计。

规则：
- 短周期 fast ∈ [3,5,8,10,15,20]，长周期 slow ∈ [20,30,40,60,90,120]
- 有效组合要求 fast < slow（否则均线无交叉意义）
- 金叉（fast 上穿 slow）做多，死叉（fast 下穿 slow）平仓
- 全部用前复权数据回测（A 股回测标准做法）
"""

import json
from pathlib import Path

FAST = [3, 5, 8, 10, 15, 20]
SLOW = [20, 30, 40, 60, 90, 120]

# 剔除 fast >= slow 的无效组合
GRID = [(f, s) for f in FAST for s in SLOW if f < s]

OUT = Path(__file__).resolve().parent.parent / "data" / "grid.json"

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {"grid": GRID, "fast_pool": FAST, "slow_pool": SLOW}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    print(f"有效组合数: {len(GRID)}")
    print(f"fast 候选: {FAST}")
    print(f"slow 候选: {SLOW}")
    print(f"网格: {GRID}")
    print(f"-> {OUT}")
